"""Unit tests for dead-letter queue (DLQ) reaper."""

import json
import os
from typing import Any

from common.ddb import (
    acquire_capacity_slot,
    create_job,
    get_capacity_in_use,
    get_job,
)
from dlq_reaper.main import lambda_handler


def test_dlq_reaper_marks_failed_and_releases_slot(mock_aws_stack: dict[str, Any]) -> None:
    """Non-terminal job in DLQ is failed with DISPATCH_FAILED code and slot released."""
    jobs_table = os.environ["JOBS_TABLE"]
    job_id = "job-poison-dlq"

    create_job(
        jobs_table,
        {
            "job_id": job_id,
            "user_id": "user-dlq",
            "status": "QUEUED",
            "stage": "QUEUED",
        },
    )
    acquire_capacity_slot(jobs_table, max_concurrent=2)
    assert get_capacity_in_use(jobs_table) == 1

    event = {
        "Records": [
            {
                "messageId": "dlq-msg-1",
                "body": json.dumps({"job_id": job_id, "user_id": "user-dlq"}),
            }
        ]
    }

    res = lambda_handler(event)
    assert res["statusCode"] == 200

    job = get_job(jobs_table, job_id)
    assert job["status"] == "FAILED"
    assert job["error"]["code"] == "DISPATCH_FAILED"
    assert "3 attempts" in job["error"]["message"]
    assert get_capacity_in_use(jobs_table) == 0


def test_dlq_reaper_ignores_terminal_jobs(mock_aws_stack: dict[str, Any]) -> None:
    """Already terminal job in DLQ is acknowledged without overwriting state."""
    jobs_table = os.environ["JOBS_TABLE"]
    job_id = "job-already-done"

    create_job(
        jobs_table,
        {
            "job_id": job_id,
            "user_id": "user-dlq",
            "status": "SUCCEEDED",
            "stage": "DONE",
            "progress": 100,
        },
    )

    event = {
        "Records": [
            {
                "messageId": "dlq-msg-2",
                "body": json.dumps({"job_id": job_id, "user_id": "user-dlq"}),
            }
        ]
    }

    res = lambda_handler(event)
    assert res["statusCode"] == 200
    job = get_job(jobs_table, job_id)
    assert job["status"] == "SUCCEEDED"
