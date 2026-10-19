"""SQS Jobs Dead-Letter Queue (DLQ) reaper Lambda handler.

Processes poison or exhausted job messages from jobs-dlq, transitions
the job to FAILED (DISPATCH_FAILED), releases capacity, and emits metrics.
"""

import json
import os
from datetime import UTC, datetime
from typing import Any

from common.ddb import (
    get_ddb_resource,
    get_job,
    release_capacity_slot_transaction,
)
from common.logging import get_logger
from common.states import TERMINAL_JOB_STATUSES, JobStatus

logger = get_logger("dlq_reaper")


def now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Process messages arriving on jobs-dlq."""
    jobs_table = os.getenv("JOBS_TABLE", "cloudtrain-dev-jobs")
    resource = get_ddb_resource()
    table = resource.Table(jobs_table)
    processed = 0

    for record in event.get("Records", []):
        raw_body = record.get("body", "{}")
        try:
            msg_data = json.loads(raw_body)
        except Exception:
            logger.error(f"DLQ message unparseable: {raw_body}")
            continue

        job_id = msg_data.get("job_id")
        user_id = msg_data.get("user_id")

        if not job_id:
            logger.warning(f"DLQ message missing job_id: {msg_data}")
            continue

        job = get_job(jobs_table, job_id)
        if not job:
            logger.info(f"Job {job_id} not found in DynamoDB during DLQ reap.")
            continue

        current_status = job.get("status")
        terminal_values = {s.value for s in TERMINAL_JOB_STATUSES}

        if current_status not in terminal_values:
            logger.error(
                f"[DLQ_REAPER_DISPATCH_FAILED] Job {job_id} for user {user_id} landed in DLQ after 3 attempts. Failing."
            )
            now_ts = now_iso()
            table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET #st = :failed, #sg = :failed, #err = :err, finished_at = :ts, updated_at = :ts",
                ExpressionAttributeNames={"#st": "status", "#sg": "stage", "#err": "error"},
                ExpressionAttributeValues={
                    ":failed": JobStatus.FAILED.value,
                    ":err": {
                        "code": "DISPATCH_FAILED",
                        "message": "The job could not be dispatched after 3 attempts",
                    },
                    ":ts": now_ts,
                },
            )
            # Release capacity slot
            release_capacity_slot_transaction(jobs_table, job_id)
        else:
            logger.info(f"Job {job_id} in DLQ is already in terminal state {current_status}; no-op.")

        processed += 1

    return {"statusCode": 200, "processed": processed}
