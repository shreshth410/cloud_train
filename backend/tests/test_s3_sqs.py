"""Unit tests for S3 and SQS helpers."""

import os

import boto3
import pytest
from moto import mock_aws

from common.s3 import (
    delete_prefix,
    generate_presigned_download,
    generate_presigned_upload,
    get_json,
    list_artifacts,
    put_json,
)
from common.sqs import enqueue_job, enqueue_status_event


@pytest.fixture
def aws_env():
    os.environ["AWS_DEFAULT_REGION"] = "ap-south-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"


@pytest.fixture
def s3_bucket(aws_env):
    with mock_aws():
        s3 = boto3.client("s3", region_name="ap-south-1")
        bucket_name = "cloudtrain-test-bucket"
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": "ap-south-1"},
        )
        yield bucket_name


@pytest.fixture
def sqs_queues(aws_env):
    with mock_aws():
        sqs = boto3.client("sqs", region_name="ap-south-1")
        jobs_q = sqs.create_queue(QueueName="cloudtrain-test-jobs")
        status_q = sqs.create_queue(QueueName="cloudtrain-test-status")
        yield {"jobs": jobs_q["QueueUrl"], "status": status_q["QueueUrl"]}


def test_s3_presigned_urls(s3_bucket):
    """Test generating presigned upload and download URLs."""
    upload_res = generate_presigned_upload(s3_bucket, "datasets/test.csv")
    assert "url" in upload_res
    assert "fields" in upload_res
    assert upload_res["fields"]["key"] == "datasets/test.csv"

    download_url = generate_presigned_download(s3_bucket, "datasets/test.csv", filename="sample.csv")
    assert "datasets/test.csv" in download_url
    assert "response-content-disposition" in download_url


def test_s3_json_and_artifacts(s3_bucket):
    """Test S3 JSON object put/get and artifact listing and prefix deletion."""
    test_data = {"accuracy": 0.98, "metrics": [1, 2, 3]}
    put_json(s3_bucket, "jobs/job-1/artifacts/metrics.json", test_data)

    retrieved = get_json(s3_bucket, "jobs/job-1/artifacts/metrics.json")
    assert retrieved == test_data

    # Put another file
    put_json(s3_bucket, "jobs/job-1/artifacts/feature_importance.json", {"f1": 0.5})

    # List artifacts
    artifacts = list_artifacts(s3_bucket, "jobs/job-1/artifacts")
    assert len(artifacts) == 2
    names = {a["name"] for a in artifacts}
    assert "metrics.json" in names
    assert "feature_importance.json" in names

    # Delete prefix
    deleted = delete_prefix(s3_bucket, "jobs/job-1/artifacts")
    assert deleted == 2
    assert len(list_artifacts(s3_bucket, "jobs/job-1/artifacts")) == 0


def test_sqs_enqueue(sqs_queues):
    """Test enqueuing job and status messages to SQS."""
    msg_id = enqueue_job(sqs_queues["jobs"], "job-101", "user-202", requeue_count=1)
    assert msg_id != ""

    event = {
        "job_id": "job-101",
        "seq": 1,
        "status": "RUNNING",
        "stage": "TRAINING",
        "progress": 30,
        "message": "Training started",
    }
    sent = enqueue_status_event(sqs_queues["status"], event)
    assert sent is True
