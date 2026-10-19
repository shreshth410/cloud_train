"""Shared pytest fixtures for CloudTrain backend test suite."""

import os
from collections.abc import Generator
from typing import Any

import boto3
import pytest
from moto import mock_aws


@pytest.fixture(autouse=True)
def aws_env() -> None:
    """Ensure AWS credentials and test environment variables are set."""
    os.environ["AWS_DEFAULT_REGION"] = "ap-south-1"
    os.environ["AWS_REGION"] = "ap-south-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"

    os.environ["ENV"] = "test"
    os.environ["DATASETS_TABLE"] = "cloudtrain-test-datasets"
    os.environ["JOBS_TABLE"] = "cloudtrain-test-jobs"
    os.environ["DATA_BUCKET"] = "cloudtrain-test-data"
    os.environ["JOBS_QUEUE_URL"] = "https://sqs.ap-south-1.amazonaws.com/123456789012/cloudtrain-test-jobs"
    os.environ["STATUS_QUEUE_URL"] = "https://sqs.ap-south-1.amazonaws.com/123456789012/cloudtrain-test-status"
    os.environ["TRAINING_LOG_GROUP"] = "/cloudtrain/test/training"
    os.environ["MAX_CONCURRENT_INSTANCES"] = "2"
    os.environ["MAX_ACTIVE_JOBS_PER_USER"] = "3"
    os.environ["MAX_DATASETS_PER_USER"] = "10"


@pytest.fixture
def mock_aws_stack(aws_env: None) -> Generator[dict[str, Any], None, None]:
    """Provide fully configured mock DynamoDB tables, S3 bucket, and SQS queues."""
    with mock_aws():
        region = "ap-south-1"
        ddb = boto3.client("dynamodb", region_name=region)
        s3 = boto3.client("s3", region_name=region)
        sqs = boto3.client("sqs", region_name=region)
        cw_logs = boto3.client("logs", region_name=region)
        ec2 = boto3.client("ec2", region_name=region)

        # 1. DynamoDB Tables
        ddb.create_table(
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

        ddb.create_table(
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
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # 2. S3 Data Bucket
        s3.create_bucket(
            Bucket="cloudtrain-test-data",
            CreateBucketConfiguration={"LocationConstraint": region},
        )

        # 3. SQS Queues
        jobs_q = sqs.create_queue(QueueName="cloudtrain-test-jobs")
        jobs_dlq = sqs.create_queue(QueueName="cloudtrain-test-jobs-dlq")
        status_q = sqs.create_queue(QueueName="cloudtrain-test-status")
        sqs.create_queue(QueueName="cloudtrain-test-status-dlq")

        os.environ["JOBS_QUEUE_URL"] = jobs_q["QueueUrl"]
        os.environ["STATUS_QUEUE_URL"] = status_q["QueueUrl"]
        os.environ["JOBS_DLQ_URL"] = jobs_dlq["QueueUrl"]

        # 4. CloudWatch Log Group
        cw_logs.create_log_group(logGroupName="/cloudtrain/test/training")

        yield {
            "ddb": ddb,
            "s3": s3,
            "sqs": sqs,
            "ec2": ec2,
            "logs": cw_logs,
            "jobs_queue_url": jobs_q["QueueUrl"],
            "status_queue_url": status_q["QueueUrl"],
            "jobs_dlq_url": jobs_dlq["QueueUrl"],
        }
