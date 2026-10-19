"""Container status reporter sending progress and state events to SQS."""

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger("cloudtrain_trainer.status")


class StatusReporter:
    """Sends container status events to the platform SQS status queue."""

    def __init__(
        self,
        job_id: str,
        queue_url: str | None = None,
        sqs_endpoint_url: str | None = None,
        region: str | None = None,
    ):
        self.job_id = job_id
        self.queue_url = queue_url or os.getenv("STATUS_QUEUE_URL")
        self.seq = 0
        self.region = region or os.getenv("AWS_REGION", "ap-south-1")
        self.sqs_endpoint_url = sqs_endpoint_url or os.getenv("SQS_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL")

        self.client = None
        if self.queue_url:
            self.client = boto3.client(
                "sqs",
                region_name=self.region,
                endpoint_url=self.sqs_endpoint_url,
            )

    def _send_event(
        self,
        event: str,
        status: str,
        stage: str,
        progress: int,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        self.seq += 1
        now_ts = datetime.now(UTC).isoformat()
        body = {
            "job_id": self.job_id,
            "seq": self.seq,
            "ts": now_ts,
            "event": event,
            "status": status,
            "stage": stage,
            "progress": max(0, min(100, progress)),
            "message": message,
            "payload": payload or {},
        }

        logger.info(f"[{status}] [{stage}] ({progress}%) - {message}")

        if not self.client or not self.queue_url:
            return True

        message_json = json.dumps(body)
        for attempt in range(1, 4):
            try:
                self.client.send_message(
                    QueueUrl=self.queue_url,
                    MessageBody=message_json,
                )
                return True
            except ClientError as e:
                logger.warning(f"Status event delivery attempt {attempt}/3 failed: {e}")
                if attempt < 3:
                    time.sleep(0.5 * (2 ** (attempt - 1)))
                else:
                    logger.error(f"Permanently failed to deliver status event seq={self.seq} after 3 attempts.")
        return False

    def stage(self, stage: str, progress: int, message: str) -> bool:
        """Report a stage transition or progress update."""
        return self._send_event(
            event="STAGE",
            status="RUNNING",
            stage=stage,
            progress=progress,
            message=message,
        )

    def metrics(self, stage: str, progress: int, summary: dict[str, Any], message: str) -> bool:
        """Report intermediate or final headline metrics summary."""
        return self._send_event(
            event="METRICS",
            status="RUNNING",
            stage=stage,
            progress=progress,
            message=message,
            payload={"metrics_summary": summary},
        )

    def succeed(self, summary: dict[str, Any] | None = None) -> bool:
        """Report job success."""
        payload = {"metrics_summary": summary} if summary else {}
        return self._send_event(
            event="SUCCEEDED",
            status="SUCCEEDED",
            stage="DONE",
            progress=100,
            message="Training completed successfully.",
            payload=payload,
        )

    def fail(self, code: str, message: str, stage: str = "DONE") -> bool:
        """Report job failure with an error code and plain-language message."""
        return self._send_event(
            event="FAILED",
            status="FAILED",
            stage=stage,
            progress=100,
            message=message,
            payload={"error": {"code": code, "message": message}},
        )
