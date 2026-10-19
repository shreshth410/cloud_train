#!/usr/bin/env python3
"""Terminate orphan training instances and clean up leaked resources."""

import argparse
import os

import boto3
from botocore.exceptions import ClientError


def cleanup(region: str = "ap-south-1", env: str = "prod") -> None:
    print(f"🧹 Scanning for orphan CloudTrain resources in {region} ({env})...")
    ec2 = boto3.client("ec2", region_name=region)
    dynamodb = boto3.resource("dynamodb", region_name=region)

    # 1. Terminate running or pending trainer EC2 instances
    try:
        resp = ec2.describe_instances(
            Filters=[
                {"Name": "tag:Project", "Values": ["CloudTrain"]},
                {
                    "Name": "instance-state-name",
                    "Values": ["pending", "running", "stopping", "stopped"],
                },
            ]
        )
        instance_ids = []
        for res in resp.get("Reservations", []):
            for inst in res.get("Instances", []):
                instance_ids.append(inst["InstanceId"])

        if instance_ids:
            print(
                f"  Terminating {len(instance_ids)} orphan EC2 instances: {instance_ids}"
            )
            ec2.terminate_instances(InstanceIds=instance_ids)
            print("  ✅ Instances termination requested.")
        else:
            print("  ✅ No orphan EC2 instances found.")
    except ClientError as e:
        print(f"  ⚠️ Error scanning EC2 instances: {e}")

    # 2. Reset DynamoDB capacity counter to 0
    jobs_table_name = f"cloudtrain-{env}-jobs"
    try:
        table = dynamodb.Table(jobs_table_name)
        table.update_item(
            Key={"user_id": "__capacity__", "job_id": "__capacity__"},
            UpdateExpression="SET in_use = :zero",
            ExpressionAttributeValues={":zero": 0},
        )
        print(f"  ✅ Reset capacity counter to 0 in {jobs_table_name}.")
    except ClientError as e:
        print(f"  ⚠️ Error updating capacity slot in DynamoDB: {e}")

    print("✨ Orphan cleanup complete.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep and terminate orphan CloudTrain instances."
    )
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "ap-south-1"))
    parser.add_argument("--env", default=os.getenv("ENV", "prod"))
    args = parser.parse_args()

    cleanup(region=args.region, env=args.env)


if __name__ == "__main__":
    main()
