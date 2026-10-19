"""SQS Jobs Queue consumer Lambda handler.

Orchestrates capacity acquisition, state transition from QUEUED to PROVISIONING,
and compute provisioning via ComputeBackend.
"""

import json
import os
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

from common.ddb import (
    acquire_capacity_slot,
    get_ddb_client,
    get_ddb_resource,
    get_job,
    release_capacity_slot,
)
from common.logging import get_logger
from common.sqs import enqueue_job
from common.states import JobStatus
from job_launcher.compute import (
    NonRetryableLaunchError,
    RetryableLaunchError,
    get_compute_backend,
)

logger = get_logger("job_launcher")


def now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Process job dispatch messages from SQS jobs queue."""
    jobs_table = os.getenv("JOBS_TABLE", "cloudtrain-dev-jobs")
    jobs_queue_url = os.getenv("JOBS_QUEUE_URL", "")
    max_concurrent = int(os.getenv("MAX_CONCURRENT_INSTANCES", "2"))

    backend = get_compute_backend()
    client = get_ddb_client()
    resource = get_ddb_resource()
    table = resource.Table(jobs_table)

    batch_item_failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        msg_id = record.get("messageId", "")
        raw_body = record.get("body", "{}")
        try:
            msg_data = json.loads(raw_body)
        except Exception:
            logger.error(f"Malformed SQS message body: {raw_body}")
            continue

        job_id = msg_data.get("job_id")
        user_id = msg_data.get("user_id")
        requeue_count = int(msg_data.get("requeue_count", 0))

        if not job_id:
            logger.warning("Message missing job_id; skipping.")
            continue

        logger.info(f"Processing launch request for job {job_id} (requeue_count={requeue_count})")

        # Step 1: Load job item
        job = get_job(jobs_table, job_id)
        if not job:
            logger.info(f"Job {job_id} not found in DynamoDB; acknowledging message.")
            continue

        current_status = job.get("status")
        if current_status != JobStatus.QUEUED.value:
            logger.info(f"Job {job_id} is in status '{current_status}' (not QUEUED); skipping idempotent dispatch.")
            continue

        # Step 2: Acquire capacity slot
        has_slot = acquire_capacity_slot(jobs_table, max_concurrent=max_concurrent)
        if not has_slot:
            if requeue_count >= 120:
                logger.error(f"Job {job_id} exceeded max capacity requeues (120). Marking FAILED.")
                now_ts = now_iso()
                table.update_item(
                    Key={"job_id": job_id},
                    UpdateExpression="SET #st = :failed, #sg = :failed, #err = :err, finished_at = :ts, updated_at = :ts",
                    ExpressionAttributeNames={"#st": "status", "#sg": "stage", "#err": "error"},
                    ExpressionAttributeValues={
                        ":failed": JobStatus.FAILED.value,
                        ":err": {
                            "code": "CAPACITY_TIMEOUT",
                            "message": "Job timed out waiting for an available capacity slot.",
                        },
                        ":ts": now_ts,
                    },
                )
                continue

            # Re-enqueue with 30s delay
            logger.info(f"Capacity full. Re-enqueueing job {job_id} with 30s delay (count={requeue_count + 1})")
            if jobs_queue_url:
                enqueue_job(
                    queue_url=jobs_queue_url,
                    job_id=job_id,
                    user_id=user_id or job.get("user_id", ""),
                    requeue_count=requeue_count + 1,
                    delay_seconds=30,
                )
            continue

        # Step 3: Conditional update QUEUED -> PROVISIONING
        now_ts = now_iso()
        try:
            client.update_item(
                TableName=jobs_table,
                Key={"job_id": {"S": job_id}},
                UpdateExpression="SET #st = :prov, #sg = :prov, updated_at = :ts",
                ConditionExpression="#st = :queued AND attribute_exists(job_id)",
                ExpressionAttributeNames={"#st": "status", "#sg": "stage"},
                ExpressionAttributeValues={
                    ":prov": {"S": JobStatus.PROVISIONING.value},
                    ":queued": {"S": JobStatus.QUEUED.value},
                    ":ts": {"S": now_ts},
                },
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.info(f"Job {job_id} state changed while acquiring slot. Releasing slot.")
                release_capacity_slot(jobs_table)
                continue
            logger.error(f"Failed to update job {job_id} to PROVISIONING: {e}")
            release_capacity_slot(jobs_table)
            batch_item_failures.append({"itemIdentifier": msg_id})
            continue

        # Step 4: Launch compute instance
        config = job.get("config", {})
        try:
            launch_res = backend.launch(job, config)
            # Record instance details
            table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET instance_id = :iid, instance_type = :itype, started_at = :sat, updated_at = :ts",
                ExpressionAttributeValues={
                    ":iid": launch_res.instance_id,
                    ":itype": launch_res.instance_type,
                    ":sat": launch_res.started_at,
                    ":ts": now_iso(),
                },
            )
            logger.info(f"Successfully launched instance {launch_res.instance_id} for job {job_id}")

        except RetryableLaunchError as rle:
            logger.warning(f"Retryable launch error for job {job_id}: {rle}. Reverting to QUEUED.")
            release_capacity_slot(jobs_table)
            # Revert to QUEUED
            try:
                table.update_item(
                    Key={"job_id": job_id},
                    UpdateExpression="SET #st = :queued, #sg = :queued, updated_at = :ts",
                    ConditionExpression="#st = :prov",
                    ExpressionAttributeNames={"#st": "status", "#sg": "stage"},
                    ExpressionAttributeValues={
                        ":queued": JobStatus.QUEUED.value,
                        ":prov": JobStatus.PROVISIONING.value,
                        ":ts": now_iso(),
                    },
                )
            except Exception as rev_err:
                logger.error(f"Failed to revert job {job_id} to QUEUED: {rev_err}")
            batch_item_failures.append({"itemIdentifier": msg_id})

        except NonRetryableLaunchError as nrle:
            logger.error(f"Non-retryable launch error for job {job_id}: {nrle}. Marking FAILED.")
            release_capacity_slot(jobs_table)
            now_ts = now_iso()
            table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET #st = :failed, #sg = :failed, #err = :err, finished_at = :ts, updated_at = :ts",
                ExpressionAttributeNames={"#st": "status", "#sg": "stage", "#err": "error"},
                ExpressionAttributeValues={
                    ":failed": JobStatus.FAILED.value,
                    ":err": {
                        "code": "LAUNCH_ERROR",
                        "message": str(nrle),
                    },
                    ":ts": now_ts,
                },
            )

        except Exception as unk_err:
            logger.exception(f"Unexpected exception launching job {job_id}: {unk_err}")
            release_capacity_slot(jobs_table)
            batch_item_failures.append({"itemIdentifier": msg_id})

    return {"batchItemFailures": batch_item_failures}
