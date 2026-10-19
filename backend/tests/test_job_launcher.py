"""Unit tests for job launcher, capacity slots, and compute provisioning."""

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch

from common.ddb import (
    acquire_capacity_slot,
    create_job,
    get_capacity_in_use,
    get_job,
)
from job_launcher.compute import (
    Ec2Backend,
    LaunchResult,
    LocalDockerBackend,
    NonRetryableLaunchError,
    RetryableLaunchError,
    get_compute_backend,
    render_user_data,
)
from job_launcher.main import lambda_handler


def make_sqs_record(job_id: str, user_id: str = "user-launch", requeue_count: int = 0) -> dict[str, Any]:
    """Craft an SQS record event."""
    body = {
        "job_id": job_id,
        "user_id": user_id,
        "requeue_count": requeue_count,
        "enqueued_at": "2026-10-19T10:00:00Z",
    }
    return {
        "Records": [
            {
                "messageId": f"msg-{job_id}",
                "body": json.dumps(body),
                "receiptHandle": "handle-123",
            }
        ]
    }


def test_launcher_idempotent_skip(mock_aws_stack: dict[str, Any]) -> None:
    """Non-existent job or non-QUEUED job is safely skipped without failures."""
    jobs_table = os.environ["JOBS_TABLE"]

    # 1. Non-existent job
    res = lambda_handler(make_sqs_record("non-existent-job"))
    assert res["batchItemFailures"] == []

    # 2. CANCELLED job
    create_job(
        jobs_table,
        {
            "job_id": "job-cancelled",
            "user_id": "user-1",
            "status": "CANCELLED",
            "stage": "CANCELLED",
        },
    )
    res = lambda_handler(make_sqs_record("job-cancelled"))
    assert res["batchItemFailures"] == []
    # Assert slot was not acquired
    assert get_capacity_in_use(jobs_table) == 0


def test_launcher_capacity_backpressure_and_timeout(mock_aws_stack: dict[str, Any]) -> None:
    """Capacity exhaustion triggers 30s re-enqueue or CAPACITY_TIMEOUT when count >= 120."""
    jobs_table = os.environ["JOBS_TABLE"]
    jobs_queue_url = os.environ["JOBS_QUEUE_URL"]
    sqs = mock_aws_stack["sqs"]

    # Fill capacity (max 2)
    acquire_capacity_slot(jobs_table, max_concurrent=2)
    acquire_capacity_slot(jobs_table, max_concurrent=2)
    assert get_capacity_in_use(jobs_table) == 2

    # Job waiting in QUEUED
    create_job(
        jobs_table,
        {
            "job_id": "job-waiting",
            "user_id": "user-1",
            "status": "QUEUED",
            "stage": "QUEUED",
        },
    )

    # 1. Re-enqueue test (requeue_count = 0)
    res = lambda_handler(make_sqs_record("job-waiting", requeue_count=0))
    assert res["batchItemFailures"] == []
    # Job remains QUEUED
    job = get_job(jobs_table, "job-waiting")
    assert job["status"] == "QUEUED"

    # Verify message re-enqueued to SQS
    q_attrs = sqs.get_queue_attributes(
        QueueUrl=jobs_queue_url,
        AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesDelayed"],
    )["Attributes"]
    total_msgs = int(q_attrs.get("ApproximateNumberOfMessages", 0)) + int(
        q_attrs.get("ApproximateNumberOfMessagesDelayed", 0)
    )
    assert total_msgs >= 1

    # 2. Timeout test (requeue_count = 120)
    create_job(
        jobs_table,
        {
            "job_id": "job-timeout",
            "user_id": "user-1",
            "status": "QUEUED",
            "stage": "QUEUED",
        },
    )
    res2 = lambda_handler(make_sqs_record("job-timeout", requeue_count=120))
    assert res2["batchItemFailures"] == []
    job2 = get_job(jobs_table, "job-timeout")
    assert job2["status"] == "FAILED"
    assert job2["error"]["code"] == "CAPACITY_TIMEOUT"


def test_launcher_successful_dispatch(mock_aws_stack: dict[str, Any]) -> None:
    """Job moves to PROVISIONING, acquires capacity slot, and records instance details."""
    jobs_table = os.environ["JOBS_TABLE"]
    job_id = "job-success-1"

    create_job(
        jobs_table,
        {
            "job_id": job_id,
            "user_id": "user-1",
            "status": "QUEUED",
            "stage": "QUEUED",
            "config": {"compute": {"size": "small"}},
        },
    )

    mock_backend = MagicMock()
    mock_backend.launch.return_value = LaunchResult(
        instance_id="i-1234567890abcdef0",
        instance_type="t3.small",
        started_at="2026-10-19T10:00:00Z",
    )

    with patch("job_launcher.main.get_compute_backend", return_value=mock_backend):
        res = lambda_handler(make_sqs_record(job_id))

    assert res["batchItemFailures"] == []
    job = get_job(jobs_table, job_id)
    assert job["status"] == "PROVISIONING"
    assert job["instance_id"] == "i-1234567890abcdef0"
    assert get_capacity_in_use(jobs_table) == 1


def test_launcher_retryable_error_reverts_to_queued(mock_aws_stack: dict[str, Any]) -> None:
    """Retryable EC2 error releases slot, reverts to QUEUED, and returns batch failure."""
    jobs_table = os.environ["JOBS_TABLE"]
    job_id = "job-retryable"

    create_job(
        jobs_table,
        {
            "job_id": job_id,
            "user_id": "user-1",
            "status": "QUEUED",
            "stage": "QUEUED",
        },
    )

    mock_backend = MagicMock()
    mock_backend.launch.side_effect = RetryableLaunchError("InsufficientInstanceCapacity")

    with patch("job_launcher.main.get_compute_backend", return_value=mock_backend):
        res = lambda_handler(make_sqs_record(job_id))

    # Reported as batch failure so SQS retries
    assert len(res["batchItemFailures"]) == 1
    # Capacity slot released
    assert get_capacity_in_use(jobs_table) == 0
    # Reverted to QUEUED
    job = get_job(jobs_table, job_id)
    assert job["status"] == "QUEUED"


def test_launcher_non_retryable_error_marks_failed(mock_aws_stack: dict[str, Any]) -> None:
    """Non-retryable error releases slot and marks job FAILED (LAUNCH_ERROR)."""
    jobs_table = os.environ["JOBS_TABLE"]
    job_id = "job-fatal"

    create_job(
        jobs_table,
        {
            "job_id": job_id,
            "user_id": "user-1",
            "status": "QUEUED",
            "stage": "QUEUED",
        },
    )

    mock_backend = MagicMock()
    mock_backend.launch.side_effect = NonRetryableLaunchError("InvalidParameterValue: Invalid subnet")

    with patch("job_launcher.main.get_compute_backend", return_value=mock_backend):
        res = lambda_handler(make_sqs_record(job_id))

    assert res["batchItemFailures"] == []
    assert get_capacity_in_use(jobs_table) == 0
    job = get_job(jobs_table, job_id)
    assert job["status"] == "FAILED"
    assert job["error"]["code"] == "LAUNCH_ERROR"


def test_render_user_data() -> None:
    """Validate user-data template substitution."""
    script = render_user_data(
        job_id="job-123",
        user_id="user-456",
        region="ap-south-1",
        data_bucket="my-bucket",
        status_queue_url="https://sqs.url",
        trainer_image="12345.dkr.ecr.ap-south-1.amazonaws.com/trainer:latest",
        max_runtime_seconds=1800,
        log_group="/cloudtrain/dev/training",
    )
    assert 'export JOB_ID="job-123"' in script
    assert 'export USER_ID="user-456"' in script
    assert 'export MAX_RUNTIME_SECONDS="1800"' in script
    assert "docker run --rm" in script


def test_ec2_backend_launch_and_terminate(mock_aws_stack: dict[str, Any]) -> None:
    """Test Ec2Backend launch and termination against moto EC2."""
    backend = Ec2Backend()
    job = {"job_id": "job-ec2-backend", "user_id": "user-ec2"}
    config = {"compute": {"size": "small"}, "max_runtime_minutes": 15}

    result = backend.launch(job, config)
    assert result.instance_id.startswith("i-")
    assert result.instance_type == "t3.small"

    backend.terminate(result.instance_id)
    backend.terminate("")


def test_local_docker_backend_launch_and_terminate() -> None:
    """Test LocalDockerBackend launch and terminate (runs in mock mode)."""
    backend = LocalDockerBackend()
    job = {"job_id": "job-local-test", "user_id": "user-local"}
    config = {"max_runtime_minutes": 10}

    result = backend.launch(job, config)
    assert result.instance_id == "local-job-local-test"
    assert result.instance_type == "local.docker"

    backend.terminate(result.instance_id)


def test_get_compute_backend_factory() -> None:
    """Factory returns LocalDockerBackend when COMPUTE_BACKEND=local, Ec2Backend otherwise."""
    os.environ["COMPUTE_BACKEND"] = "local"
    assert isinstance(get_compute_backend(), LocalDockerBackend)

    os.environ["COMPUTE_BACKEND"] = "ec2"
    assert isinstance(get_compute_backend(), Ec2Backend)
