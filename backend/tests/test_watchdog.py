"""Unit tests for watchdog health checks, timeouts, and capacity reconciliation."""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from common.ddb import (
    acquire_capacity_slot,
    create_dataset,
    create_job,
    get_capacity_in_use,
    get_dataset,
    get_job,
    set_capacity_in_use,
)
from watchdog.main import lambda_handler


def test_watchdog_runtime_timeout(mock_aws_stack: dict[str, Any]) -> None:
    """Job exceeding runtime limit + 10 min is marked TIMED_OUT and slot released."""
    jobs_table = os.environ["JOBS_TABLE"]
    job_id = "job-timed-out"

    past_time = (datetime.now(UTC) - timedelta(minutes=45)).isoformat()

    create_job(
        jobs_table,
        {
            "job_id": job_id,
            "user_id": "user-watch",
            "status": "RUNNING",
            "stage": "TRAINING",
            "progress": 50,
            "started_at": past_time,
            "last_event_at": past_time,
            "updated_at": past_time,
            "config": {"max_runtime_minutes": 30},
        },
    )
    acquire_capacity_slot(jobs_table, max_concurrent=2)
    assert get_capacity_in_use(jobs_table) == 1

    res = lambda_handler({})
    assert res["statusCode"] == 200

    job = get_job(jobs_table, job_id)
    assert job["status"] == "TIMED_OUT"
    assert job["error"]["code"] == "RUNTIME_TIMEOUT"
    assert get_capacity_in_use(jobs_table) == 0


def test_watchdog_boot_timeout(mock_aws_stack: dict[str, Any]) -> None:
    """Job stuck in PROVISIONING for > 15 min is marked FAILED (BOOT_TIMEOUT)."""
    jobs_table = os.environ["JOBS_TABLE"]
    job_id = "job-boot-stuck"

    past_time = (datetime.now(UTC) - timedelta(minutes=20)).isoformat()

    create_job(
        jobs_table,
        {
            "job_id": job_id,
            "user_id": "user-watch",
            "status": "PROVISIONING",
            "stage": "BOOTSTRAP",
            "started_at": past_time,
            "updated_at": past_time,
        },
    )
    acquire_capacity_slot(jobs_table, max_concurrent=2)

    res = lambda_handler({})
    assert res["statusCode"] == 200

    job = get_job(jobs_table, job_id)
    assert job["status"] == "FAILED"
    assert job["error"]["code"] == "BOOT_TIMEOUT"
    assert get_capacity_in_use(jobs_table) == 0


def test_watchdog_lost_instance(mock_aws_stack: dict[str, Any]) -> None:
    """Instance terminated in EC2 while job non-terminal is marked FAILED (INSTANCE_LOST)."""
    jobs_table = os.environ["JOBS_TABLE"]
    job_id = "job-lost"
    ec2 = mock_aws_stack["ec2"]

    # Launch EC2 instance
    inst_resp = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)
    inst_id = inst_resp["Instances"][0]["InstanceId"]
    # Immediately terminate it
    ec2.terminate_instances(InstanceIds=[inst_id])

    past_time = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()

    create_job(
        jobs_table,
        {
            "job_id": job_id,
            "user_id": "user-watch",
            "status": "RUNNING",
            "stage": "TRAINING",
            "instance_id": inst_id,
            "last_event_at": past_time,
            "updated_at": past_time,
        },
    )
    acquire_capacity_slot(jobs_table, max_concurrent=2)

    res = lambda_handler({})
    assert res["statusCode"] == 200

    job = get_job(jobs_table, job_id)
    assert job["status"] == "FAILED"
    assert job["error"]["code"] == "INSTANCE_LOST"
    assert get_capacity_in_use(jobs_table) == 0


def test_watchdog_abandoned_dataset_cleanup(mock_aws_stack: dict[str, Any]) -> None:
    """PENDING_UPLOAD dataset older than 1 hr with no S3 object is purged."""
    datasets_table = os.environ["DATASETS_TABLE"]
    ds_id = "ds-abandoned"

    past_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()

    create_dataset(
        datasets_table,
        {
            "dataset_id": ds_id,
            "user_id": "user-abandoned",
            "status": "PENDING_UPLOAD",
            "s3_key": f"datasets/user-abandoned/{ds_id}/data.csv",
            "created_at": past_time,
            "updated_at": past_time,
        },
    )

    lambda_handler({})
    assert get_dataset(datasets_table, ds_id) is None


def test_watchdog_capacity_reconciliation(mock_aws_stack: dict[str, Any]) -> None:
    """Drifted in_use capacity counter is corrected to match active non-terminal jobs."""
    jobs_table = os.environ["JOBS_TABLE"]

    # Deliberately set counter to 5
    set_capacity_in_use(jobs_table, 5)
    assert get_capacity_in_use(jobs_table) == 5

    # Exactly 1 active job
    create_job(
        jobs_table,
        {
            "job_id": "job-active-reconcile",
            "user_id": "user-1",
            "status": "RUNNING",
            "stage": "TRAINING",
            "slot_released": False,
        },
    )

    lambda_handler({})

    # Corrected to 1
    assert get_capacity_in_use(jobs_table) == 1


def test_watchdog_orphan_instance_cleanup(mock_aws_stack: dict[str, Any]) -> None:
    """Orphan EC2 trainer instance associated with completed job is terminated."""
    jobs_table = os.environ["JOBS_TABLE"]
    ec2 = mock_aws_stack["ec2"]

    # Seed terminal job
    create_job(
        jobs_table,
        {
            "job_id": "job-completed-orphan",
            "user_id": "user-1",
            "status": "SUCCEEDED",
            "stage": "DONE",
        },
    )

    # Launch instance with tags
    inst_resp = ec2.run_instances(
        ImageId="ami-12345678",
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Project", "Value": "cloudtrain"},
                    {"Key": "Role", "Value": "trainer"},
                    {"Key": "JobId", "Value": "job-completed-orphan"},
                ],
            }
        ],
    )
    inst_id = inst_resp["Instances"][0]["InstanceId"]

    # Run watchdog
    res = lambda_handler({})
    assert res["statusCode"] == 200

    # Assert instance terminated
    desc = ec2.describe_instances(InstanceIds=[inst_id])
    state = desc["Reservations"][0]["Instances"][0]["State"]["Name"]
    assert state in ("terminated", "shutting-down")
