"""Unit tests for status updater SQS consumer."""

import json
import os
import uuid
from typing import Any

from common.ddb import (
    acquire_capacity_slot,
    create_job,
    get_capacity_in_use,
    get_job,
)
from status_updater.main import lambda_handler


def make_status_record(event: dict[str, Any]) -> dict[str, Any]:
    """Helper to wrap status event in SQS record."""
    return {
        "Records": [
            {
                "messageId": f"msg-{event.get('seq')}",
                "body": json.dumps(event),
            }
        ]
    }


def test_status_event_progression_and_capacity_release(mock_aws_stack: dict[str, Any]) -> None:
    """Verify linear progression of status events and atomic slot release on terminal event."""
    jobs_table = os.environ["JOBS_TABLE"]
    job_id = str(uuid.uuid4())

    create_job(
        jobs_table,
        {
            "job_id": job_id,
            "user_id": "user-1",
            "status": "PROVISIONING",
            "stage": "BOOTSTRAP",
            "progress": 5,
        },
    )

    # Acquire capacity slot initially
    acquire_capacity_slot(jobs_table, max_concurrent=2)
    assert get_capacity_in_use(jobs_table) == 1

    # Event 1: RUNNING / TRAINING
    ev1 = {
        "job_id": job_id,
        "seq": 1,
        "ts": "2026-10-19T10:00:00Z",
        "event": "STAGE",
        "status": "RUNNING",
        "stage": "TRAINING",
        "progress": 40,
        "message": "Fitting model",
    }
    lambda_handler(make_status_record(ev1))
    j1 = get_job(jobs_table, job_id)
    assert j1["status"] == "RUNNING"
    assert j1["stage"] == "TRAINING"
    assert j1["progress"] == 40
    assert j1["last_seq"] == 1
    assert get_capacity_in_use(jobs_table) == 1  # Slot still held

    # Event 2: Stale/duplicate event (seq=1 again) ignored
    ev1_dup = {
        "job_id": job_id,
        "seq": 1,
        "ts": "2026-10-19T10:00:01Z",
        "event": "STAGE",
        "status": "RUNNING",
        "stage": "TRAINING",
        "progress": 50,
        "message": "Duplicate",
    }
    lambda_handler(make_status_record(ev1_dup))
    assert get_job(jobs_table, job_id)["progress"] == 40  # Unchanged

    # Event 3: Terminal SUCCEEDED event with metrics
    ev_succ = {
        "job_id": job_id,
        "seq": 2,
        "ts": "2026-10-19T10:00:05Z",
        "event": "SUCCEEDED",
        "status": "SUCCEEDED",
        "stage": "DONE",
        "progress": 100,
        "message": "Training finished successfully",
        "payload": {"metrics_summary": {"accuracy": 0.95}},
    }
    lambda_handler(make_status_record(ev_succ))
    j_final = get_job(jobs_table, job_id)
    assert j_final["status"] == "SUCCEEDED"
    assert j_final["stage"] == "DONE"
    assert j_final["progress"] == 100
    assert j_final["metrics_summary"]["accuracy"] == 0.95
    assert "finished_at" in j_final
    assert j_final.get("slot_released") is True

    # Capacity slot released!
    assert get_capacity_in_use(jobs_table) == 0


def test_bootstrap_failure_seq_zero(mock_aws_stack: dict[str, Any]) -> None:
    """Bootstrap seq=0 failure event is accepted when last_seq is absent."""
    jobs_table = os.environ["JOBS_TABLE"]
    job_id = str(uuid.uuid4())

    create_job(
        jobs_table,
        {
            "job_id": job_id,
            "user_id": "user-1",
            "status": "PROVISIONING",
            "stage": "BOOTSTRAP",
        },
    )
    acquire_capacity_slot(jobs_table, max_concurrent=2)

    ev_boot = {
        "job_id": job_id,
        "seq": 0,
        "ts": "2026-10-19T10:00:00Z",
        "event": "FAILED",
        "status": "FAILED",
        "stage": "BOOTSTRAP",
        "progress": 0,
        "message": "docker install failed",
        "payload": {"error": {"code": "BOOTSTRAP_FAILED", "message": "docker install failed"}},
    }
    lambda_handler(make_status_record(ev_boot))
    job = get_job(jobs_table, job_id)
    assert job["status"] == "FAILED"
    assert job["error"]["code"] == "BOOTSTRAP_FAILED"
    assert get_capacity_in_use(jobs_table) == 0
