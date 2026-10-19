#!/usr/bin/env python3
"""Bootstrap local AWS emulator (LocalStack/MiniStack) resources.

Creates S3 buckets, SQS queues, DynamoDB tables, and capacity slot items.
Usage: python scripts/bootstrap_local.py [--endpoint http://localhost:4566]
"""

import argparse
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError


def get_clients(endpoint_url: str, region: str = "ap-south-1") -> tuple[Any, Any, Any]:
    """Create boto3 clients targeted at local emulator."""
    session = boto3.Session(
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name=region,
    )
    s3 = session.client("s3", endpoint_url=endpoint_url)
    ddb = session.client("dynamodb", endpoint_url=endpoint_url)
    sqs = session.client("sqs", endpoint_url=endpoint_url)
    return s3, ddb, sqs


def bootstrap_local_resources(endpoint_url: str, region: str = "ap-south-1") -> None:
    """Create all required local CloudTrain AWS resources."""
    s3, ddb, sqs = get_clients(endpoint_url, region)

    # 1. S3 Bucket
    bucket_name = "cloudtrain-local-data"
    print(f"Creating S3 bucket: {bucket_name}...")
    try:
        s3.create_bucket(
            Bucket=bucket_name,
            CreateBucketConfiguration={"LocationConstraint": region},
        )
        print(f"  [OK] Bucket {bucket_name} created.")
    except ClientError as e:
        if e.response["Error"]["Code"] in (
            "BucketAlreadyOwnedByYou",
            "BucketAlreadyExists",
        ):
            print(f"  [OK] Bucket {bucket_name} already exists.")
        else:
            print(f"  [WARN] S3 creation warning: {e}")

    # 2. SQS Queues
    queues = [
        "cloudtrain-local-jobs",
        "cloudtrain-local-jobs-dlq",
        "cloudtrain-local-status",
        "cloudtrain-local-status-dlq",
    ]
    for q_name in queues:
        print(f"Creating SQS queue: {q_name}...")
        try:
            sqs.create_queue(QueueName=q_name)
            print(f"  [OK] Queue {q_name} created.")
        except ClientError as e:
            print(f"  [WARN] SQS creation warning: {e}")

    # 3. DynamoDB Datasets Table
    ds_table = "cloudtrain-local-datasets"
    print(f"Creating DynamoDB table: {ds_table}...")
    try:
        ddb.create_table(
            TableName=ds_table,
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
        print(f"  [OK] Table {ds_table} created.")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"  [OK] Table {ds_table} already exists.")
        else:
            print(f"  [WARN] DynamoDB creation warning: {e}")

    # 4. DynamoDB Jobs Table
    jobs_table = "cloudtrain-local-jobs"
    print(f"Creating DynamoDB table: {jobs_table}...")
    try:
        ddb.create_table(
            TableName=jobs_table,
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
        print(f"  [OK] Table {jobs_table} created.")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceInUseException":
            print(f"  [OK] Table {jobs_table} already exists.")
        else:
            print(f"  [WARN] DynamoDB creation warning: {e}")

    # 5. Initialize Capacity Slot Item
    print(f"Initializing capacity slot item in {jobs_table}...")
    try:
        ddb.put_item(
            TableName=jobs_table,
            Item={
                "job_id": {"S": "__capacity__"},
                "in_use": {"N": "0"},
            },
        )
        print("  [OK] Capacity slot initialized to 0.")
    except ClientError as e:
        print(f"  [WARN] Capacity slot warning: {e}")

    print("\n[SUCCESS] Local AWS emulator bootstrap complete!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap local AWS resources.")
    parser.add_argument(
        "--endpoint",
        default=os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566"),
        help="LocalStack / emulator endpoint URL",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_DEFAULT_REGION", "ap-south-1"),
        help="AWS region",
    )
    args = parser.parse_args()
    bootstrap_local_resources(args.endpoint, args.region)


if __name__ == "__main__":
    main()
