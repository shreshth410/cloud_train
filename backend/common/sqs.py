"""SQS messaging access layer for jobs and status queues."""

import json
import os
import time
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.logging import get_logger

logger = get_logger("sqs")


def get_sqs_client() -> Any:
    """Create or return an SQS client, supporting local emulator via SQS_ENDPOINT_URL."""
    endpoint_url = os.getenv("SQS_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL")
    return boto3.client("sqs", endpoint_url=endpoint_url)


def enqueue_job(
    queue_url: str,
    job_id: str,
    user_id: str,
    requeue_count: int = 0,
    delay_seconds: int = 0,
) -> str:
    """Enqueue a job dispatch message onto the jobs queue."""
    client = get_sqs_client()
    body = {
        "job_id": job_id,
        "user_id": user_id,
        "requeue_count": requeue_count,
        "enqueued_at": datetime.now(UTC).isoformat(),
    }
    kwargs: dict[str, Any] = {
        "QueueUrl": queue_url,
        "MessageBody": json.dumps(body),
        "MessageAttributes": {
            "schema_version": {
                "DataType": "Number",
                "StringValue": "1",
            }
        },
    }
    if delay_seconds > 0:
        kwargs["DelaySeconds"] = min(delay_seconds, 900)

    resp = client.send_message(**kwargs)
    logger.info(f"Enqueued job {job_id} (msg_id={resp.get('MessageId')})")
    return resp.get("MessageId", "")


def enqueue_status_event(
    queue_url: str,
    event: dict[str, Any],
    max_retries: int = 3,
) -> bool:
    """Enqueue a container status event onto the status queue with exponential backoff."""
    client = get_sqs_client()
    body = json.dumps(event)

    for attempt in range(1, max_retries + 1):
        try:
            client.send_message(
                QueueUrl=queue_url,
                MessageBody=body,
            )
            return True
        except ClientError as e:
            logger.warning(
                f"Failed to send status event (seq={event.get('seq')}, attempt {attempt}/{max_retries}): {e}"
            )
            if attempt < max_retries:
                time.sleep(0.5 * (2 ** (attempt - 1)))
            else:
                logger.error(
                    f"Permanently failed to send status event seq={event.get('seq')} after {max_retries} attempts."
                )
                return False
    return False
