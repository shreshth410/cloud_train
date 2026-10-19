"""SQS Status Queue consumer Lambda handler.

Applies training container status events to DynamoDB jobs table with
monotonic sequence enforcement, rank progression, and capacity slot release.
"""

import json
import os
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

from common.ddb import (
    get_ddb_client,
    release_capacity_slot_transaction,
)
from common.logging import get_logger
from common.schemas import validate_status_event
from common.states import TERMINAL_JOB_STATUSES, JobStatus

logger = get_logger("status_updater")


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


def apply_event_to_job(jobs_table: str, event: dict[str, Any]) -> bool:
    """Apply a status event to DynamoDB with condition checks and capacity release.

    Returns True if update succeeded, False if event was stale, out of order, or job already terminal.
    """
    job_id = event["job_id"]
    seq = int(event["seq"])
    status = event["status"]
    stage = event["stage"]
    progress = int(event["progress"])
    message = event.get("message", "")
    ts = event.get("ts", now_iso())
    payload = event.get("payload", {})

    client = get_ddb_client()

    update_parts = [
        "#st = :status",
        "#sg = :stage",
        "#pr = :progress",
        "#msg = :message",
        "#ls = :seq",
        "#lea = :ts",
        "#ua = :ts",
    ]
    expr_names = {
        "#st": "status",
        "#sg": "stage",
        "#pr": "progress",
        "#msg": "message",
        "#ls": "last_seq",
        "#lea": "last_event_at",
        "#ua": "updated_at",
    }
    expr_values: dict[str, Any] = {
        ":status": {"S": status},
        ":stage": {"S": stage},
        ":progress": {"N": str(progress)},
        ":message": {"S": message},
        ":seq": {"N": str(seq)},
        ":ts": {"S": ts},
        ":succ": {"S": JobStatus.SUCCEEDED.value},
        ":fail": {"S": JobStatus.FAILED.value},
        ":canc": {"S": JobStatus.CANCELLED.value},
        ":tout": {"S": JobStatus.TIMED_OUT.value},
    }

    if "metrics_summary" in payload:
        ms_dict = {}
        for k, v in payload["metrics_summary"].items():
            if isinstance(v, (int, float)):
                ms_dict[k] = {"N": str(v)}
            else:
                ms_dict[k] = {"S": str(v)}
        update_parts.append("#ms = :ms")
        expr_names["#ms"] = "metrics_summary"
        expr_values[":ms"] = {"M": ms_dict}

    if "error" in payload:
        err = payload["error"]
        update_parts.append("#err = :err")
        expr_names["#err"] = "error"
        expr_values[":err"] = {
            "M": {
                "code": {"S": str(err.get("code", "UNKNOWN"))},
                "message": {"S": str(err.get("message", ""))},
            }
        }

    is_terminal = status in {s.value for s in TERMINAL_JOB_STATUSES}
    if is_terminal:
        update_parts.append("finished_at = :ts")

    # Sequence condition check
    # Bootstrap failure special case: seq=0 only allowed for FAILED when last_seq is absent
    if seq == 0:
        if status != JobStatus.FAILED.value:
            logger.warning(f"Dropping seq=0 event with non-FAILED status: {status}")
            return False
        cond_expr = (
            "attribute_exists(job_id) AND attribute_not_exists(last_seq) AND NOT #st IN (:succ, :fail, :canc, :tout)"
        )
    else:
        cond_expr = (
            "attribute_exists(job_id) "
            "AND (attribute_not_exists(last_seq) OR last_seq < :seq) "
            "AND NOT #st IN (:succ, :fail, :canc, :tout)"
        )

    try:
        client.update_item(
            TableName=jobs_table,
            Key={"job_id": {"S": job_id}},
            UpdateExpression="SET " + ", ".join(update_parts),
            ConditionExpression=cond_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )
        logger.info(f"Updated job {job_id}: status={status}, stage={stage}, seq={seq}")

        # If entering terminal state, release capacity slot
        if is_terminal:
            logger.info(f"Job {job_id} reached terminal state {status}; releasing capacity slot.")
            release_capacity_slot_transaction(jobs_table, job_id)

        return True

    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.info(f"Condition check failed for event seq={seq} on job {job_id}; ignoring stale/duplicate event.")
            return False
        logger.error(f"Error updating job {job_id} with event seq={seq}: {e}")
        raise


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Process batch of status events from SQS status queue."""
    jobs_table = os.getenv("JOBS_TABLE", "cloudtrain-dev-jobs")
    batch_item_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        msg_id = record.get("messageId", "")
        raw_body = record.get("body", "{}")
        try:
            event_dict = json.loads(raw_body)
        except Exception:
            logger.error(f"Invalid JSON in status message: {raw_body}")
            continue

        try:
            validate_status_event(event_dict)
        except Exception as ve:
            logger.warning(f"Dropping invalid status event ({ve}): {event_dict}")
            continue

        try:
            apply_event_to_job(jobs_table, event_dict)
        except Exception as exc:
            logger.exception(f"Failed to process status message {msg_id}: {exc}")
            batch_item_failures.append({"itemIdentifier": msg_id})

    return {"batchItemFailures": batch_item_failures}
