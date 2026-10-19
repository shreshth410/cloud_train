"""Unit tests for DynamoDB operations, capacity management, and status updates."""

import os

import boto3
import pytest
from moto import mock_aws

from common.ddb import (
    acquire_capacity_slot,
    apply_status_event,
    count_user_active_jobs,
    count_user_datasets,
    create_dataset,
    create_job,
    get_capacity_in_use,
    get_job,
    release_capacity_slot,
    release_capacity_slot_transaction,
)


@pytest.fixture
def aws_env():
    os.environ["AWS_DEFAULT_REGION"] = "ap-south-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"


@pytest.fixture
def ddb_tables(aws_env):
    with mock_aws():
        client = boto3.client("dynamodb", region_name="ap-south-1")

        # Create jobs table
        client.create_table(
            TableName="cloudtrain-test-jobs",
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "updated_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "user-created-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "status-updated-index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "updated_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Create datasets table
        client.create_table(
            TableName="cloudtrain-test-datasets",
            KeySchema=[{"AttributeName": "dataset_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "dataset_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "user-created-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield {"jobs": "cloudtrain-test-jobs", "datasets": "cloudtrain-test-datasets"}


def test_capacity_slot_acquire_and_release(ddb_tables):
    """Test atomic capacity slot acquisition and max_concurrency enforcement."""
    table = ddb_tables["jobs"]
    assert get_capacity_in_use(table) == 0

    # Acquire slot 1 (max 2)
    assert acquire_capacity_slot(table, max_concurrent=2) is True
    assert get_capacity_in_use(table) == 1

    # Acquire slot 2 (max 2)
    assert acquire_capacity_slot(table, max_concurrent=2) is True
    assert get_capacity_in_use(table) == 2

    # Attempt to acquire slot 3 when full -> should fail
    assert acquire_capacity_slot(table, max_concurrent=2) is False
    assert get_capacity_in_use(table) == 2

    # Release one slot
    assert release_capacity_slot(table) is True
    assert get_capacity_in_use(table) == 1

    # Now can acquire again
    assert acquire_capacity_slot(table, max_concurrent=2) is True
    assert get_capacity_in_use(table) == 2


def test_capacity_slot_transactional_release_once(ddb_tables):
    """Test that releasing slot for a job releases exactly once and marks slot_released."""
    table = ddb_tables["jobs"]
    job_id = "job-1234"

    # Create job and acquire capacity
    create_job(table, {"job_id": job_id, "user_id": "user-1", "status": "RUNNING"})
    acquire_capacity_slot(table, max_concurrent=2)
    assert get_capacity_in_use(table) == 1

    # First release should succeed
    assert release_capacity_slot_transaction(table, job_id) is True
    assert get_capacity_in_use(table) == 0

    # Second release for the same job should fail gracefully (idempotent)
    assert release_capacity_slot_transaction(table, job_id) is False
    assert get_capacity_in_use(table) == 0


def test_apply_status_event_ordering(ddb_tables):
    """Test applying status events enforces sequence number and avoids terminal overwrites."""
    table = ddb_tables["jobs"]
    job_id = "job-5678"

    create_job(
        table,
        {
            "job_id": job_id,
            "user_id": "user-1",
            "status": "QUEUED",
            "stage": "BOOTSTRAP",
            "progress": 0,
        },
    )

    # Event 1: RUNNING
    event1 = {
        "job_id": job_id,
        "seq": 1,
        "ts": "2026-10-19T10:00:00Z",
        "status": "RUNNING",
        "stage": "TRAINING",
        "progress": 50,
        "payload": {"metrics_summary": {"loss": 0.2}},
    }
    assert apply_status_event(table, event1) is True

    job = get_job(table, job_id)
    assert job["status"] == "RUNNING"
    assert job["last_seq"] == 1
    assert job["progress"] == 50

    # Event with older or duplicate sequence (seq=1) should be ignored
    dup_event = dict(event1, progress=60)
    assert apply_status_event(table, dup_event) is False

    # Event with seq 2: SUCCEEDED
    event2 = {
        "job_id": job_id,
        "seq": 2,
        "ts": "2026-10-19T10:05:00Z",
        "status": "SUCCEEDED",
        "stage": "DONE",
        "progress": 100,
        "payload": {"metrics_summary": {"accuracy": 0.95}},
    }
    assert apply_status_event(table, event2) is True

    job = get_job(table, job_id)
    assert job["status"] == "SUCCEEDED"
    assert job["progress"] == 100

    # Event arriving after terminal state is ignored
    late_event = {
        "job_id": job_id,
        "seq": 3,
        "ts": "2026-10-19T10:06:00Z",
        "status": "RUNNING",
        "stage": "TRAINING",
        "progress": 70,
    }
    assert apply_status_event(table, late_event) is False
    job = get_job(table, job_id)
    assert job["status"] == "SUCCEEDED"


def test_user_quotas_and_counts(ddb_tables):
    """Test counting active jobs and datasets for a user."""
    jobs_tbl = ddb_tables["jobs"]
    ds_tbl = ddb_tables["datasets"]
    uid = "user-abc"

    assert count_user_active_jobs(jobs_tbl, uid) == 0
    assert count_user_datasets(ds_tbl, uid) == 0

    # Add 2 active jobs and 1 terminal job
    create_job(jobs_tbl, {"job_id": "j1", "user_id": uid, "status": "QUEUED"})
    create_job(jobs_tbl, {"job_id": "j2", "user_id": uid, "status": "RUNNING"})
    create_job(jobs_tbl, {"job_id": "j3", "user_id": uid, "status": "SUCCEEDED"})

    assert count_user_active_jobs(jobs_tbl, uid) == 2

    # Add datasets
    create_dataset(ds_tbl, {"dataset_id": "d1", "user_id": uid, "status": "READY"})
    create_dataset(ds_tbl, {"dataset_id": "d2", "user_id": uid, "status": "READY"})

    assert count_user_datasets(ds_tbl, uid) == 2
