"""Watchdog periodic maintenance and health check Lambda handler.

Runs every 5 minutes to detect timed-out jobs, lost instances, boot timeouts,
clean orphan trainer instances and abandoned datasets, and reconcile capacity counter.
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.ddb import (
    get_capacity_in_use,
    get_ddb_resource,
    get_job,
    release_capacity_slot_transaction,
    set_capacity_in_use,
)
from common.logging import get_logger
from common.s3 import get_s3_client
from common.states import TERMINAL_JOB_STATUSES, JobStatus

logger = get_logger("watchdog")


def parse_iso(ts_str: str | None) -> datetime | None:
    """Safely parse an ISO-8601 string to aware UTC datetime."""
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except Exception:
        return None


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


def terminate_ec2_instance(region: str, instance_id: str) -> None:
    """Terminate an EC2 instance with tag safety check."""
    if not instance_id or instance_id.startswith("local-"):
        return
    ec2 = boto3.client("ec2", region_name=region)
    try:
        logger.info(f"Watchdog terminating EC2 instance {instance_id}")
        ec2.terminate_instances(InstanceIds=[instance_id])
    except Exception as e:
        logger.warning(f"Watchdog failed to terminate {instance_id}: {e}")


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Execute periodic watchdog scan and reconciliation."""
    jobs_table = os.getenv("JOBS_TABLE", "cloudtrain-dev-jobs")
    datasets_table = os.getenv("DATASETS_TABLE", "cloudtrain-dev-datasets")
    data_bucket = os.getenv("DATA_BUCKET", "cloudtrain-dev-data")
    region = os.getenv("AWS_REGION", "ap-south-1")
    default_max_runtime_mins = int(os.getenv("MAX_RUNTIME_MINUTES", "60"))

    now = datetime.now(UTC)
    now_ts = now.isoformat()

    resource = get_ddb_resource()
    table = resource.Table(jobs_table)
    ec2 = boto3.client("ec2", region_name=region)

    # ──────────────────────────────────────────────
    # 1. Active Job Health Checks
    # ──────────────────────────────────────────────
    active_statuses = [
        JobStatus.PROVISIONING.value,
        JobStatus.RUNNING.value,
        JobStatus.UPLOADING.value,
    ]

    active_jobs: list[dict[str, Any]] = []

    for status_val in active_statuses:
        try:
            resp = table.query(
                IndexName="status-updated-index",
                KeyConditionExpression="#st = :st",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={":st": status_val},
            )
            active_jobs.extend(resp.get("Items", []))
        except Exception as e:
            logger.warning(f"Error querying status-updated-index for {status_val}: {e}")

    logger.info(f"Watchdog found {len(active_jobs)} active non-terminal jobs.")

    for job in active_jobs:
        job_id = job["job_id"]
        status = job.get("status")
        config = job.get("config", {})
        max_runtime_mins = int(config.get("max_runtime_minutes", default_max_runtime_mins))
        instance_id = job.get("instance_id")

        last_event_dt = (
            parse_iso(job.get("last_event_at"))
            or parse_iso(job.get("started_at"))
            or parse_iso(job.get("updated_at"))
            or parse_iso(job.get("created_at"))
        )

        started_dt = parse_iso(job.get("started_at")) or parse_iso(job.get("created_at"))

        # A) Runtime Timeout: now - last_event_at > max_runtime_minutes + 10 min
        if last_event_dt and (now - last_event_dt) > timedelta(minutes=max_runtime_mins + 10):
            logger.error(f"Job {job_id} exceeded runtime timeout (last event was {last_event_dt}). Timing out.")
            if instance_id:
                terminate_ec2_instance(region, instance_id)
            table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET #st = :tout, #sg = :tout, #err = :err, finished_at = :ts, updated_at = :ts",
                ExpressionAttributeNames={"#st": "status", "#sg": "stage", "#err": "error"},
                ExpressionAttributeValues={
                    ":tout": JobStatus.TIMED_OUT.value,
                    ":err": {
                        "code": "RUNTIME_TIMEOUT",
                        "message": f"Training runtime exceeded allocated limit of {max_runtime_mins} minutes.",
                    },
                    ":ts": now_ts,
                },
            )
            release_capacity_slot_transaction(jobs_table, job_id)
            continue

        # B) Boot Timeout: status == PROVISIONING for > 15 minutes with no events
        if status == JobStatus.PROVISIONING.value and started_dt and (now - started_dt) > timedelta(minutes=15):
            logger.error(f"Job {job_id} stuck in PROVISIONING for > 15 minutes. Marking FAILED (BOOT_TIMEOUT).")
            if instance_id:
                terminate_ec2_instance(region, instance_id)
            table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET #st = :fail, #sg = :fail, #err = :err, finished_at = :ts, updated_at = :ts",
                ExpressionAttributeNames={"#st": "status", "#sg": "stage", "#err": "error"},
                ExpressionAttributeValues={
                    ":fail": JobStatus.FAILED.value,
                    ":err": {
                        "code": "BOOT_TIMEOUT",
                        "message": "Instance provisioning and container bootstrap timed out after 15 minutes.",
                    },
                    ":ts": now_ts,
                },
            )
            release_capacity_slot_transaction(jobs_table, job_id)
            continue

        # C) Lost Instance: EC2 instance is terminated/shutting-down while job is non-terminal for > 2 min
        if instance_id and not instance_id.startswith("local-"):
            try:
                desc = ec2.describe_instances(InstanceIds=[instance_id])
                reservations = desc.get("Reservations", [])
                if reservations and reservations[0].get("Instances"):
                    inst_state = reservations[0]["Instances"][0]["State"]["Name"]
                    if (
                        inst_state in ("terminated", "shutting-down")
                        and last_event_dt
                        and (now - last_event_dt) > timedelta(minutes=2)
                    ):
                        logger.error(
                            f"Instance {instance_id} for job {job_id} is {inst_state} without completing. Failing (INSTANCE_LOST)."
                        )
                        table.update_item(
                            Key={"job_id": job_id},
                            UpdateExpression="SET #st = :fail, #sg = :fail, #err = :err, finished_at = :ts, updated_at = :ts",
                            ExpressionAttributeNames={"#st": "status", "#sg": "stage", "#err": "error"},
                            ExpressionAttributeValues={
                                ":fail": JobStatus.FAILED.value,
                                ":err": {
                                    "code": "INSTANCE_LOST",
                                    "message": "Compute instance terminated unexpectedly without reporting completion.",
                                },
                                ":ts": now_ts,
                            },
                        )
                        release_capacity_slot_transaction(jobs_table, job_id)
            except ClientError as e:
                err_code = e.response["Error"]["Code"]
                if err_code == "InvalidInstanceID.NotFound":
                    logger.error(f"Instance {instance_id} for job {job_id} not found in EC2. Marking INSTANCE_LOST.")
                    table.update_item(
                        Key={"job_id": job_id},
                        UpdateExpression="SET #st = :fail, #sg = :fail, #err = :err, finished_at = :ts, updated_at = :ts",
                        ExpressionAttributeNames={"#st": "status", "#sg": "stage", "#err": "error"},
                        ExpressionAttributeValues={
                            ":fail": JobStatus.FAILED.value,
                            ":err": {
                                "code": "INSTANCE_LOST",
                                "message": "Compute instance not found in AWS EC2.",
                            },
                            ":ts": now_ts,
                        },
                    )
                    release_capacity_slot_transaction(jobs_table, job_id)

    # ──────────────────────────────────────────────
    # 2. Terminate Orphan EC2 Instances
    # ──────────────────────────────────────────────
    try:
        desc = ec2.describe_instances(
            Filters=[
                {"Name": "tag:Project", "Values": ["cloudtrain"]},
                {"Name": "tag:Role", "Values": ["trainer"]},
                {"Name": "instance-state-name", "Values": ["pending", "running"]},
            ]
        )
        for res in desc.get("Reservations", []):
            for inst in res.get("Instances", []):
                inst_id = inst["InstanceId"]
                launch_time = inst["LaunchTime"]
                if launch_time.tzinfo is None:
                    launch_time = launch_time.replace(tzinfo=UTC)

                # Extract JobId tag
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                tagged_job_id = tags.get("JobId")

                should_terminate = False
                reason = ""

                # Older than max_runtime + 30 min
                if (now - launch_time) > timedelta(minutes=default_max_runtime_mins + 30):
                    should_terminate = True
                    reason = "Instance lifetime exceeded max runtime + 30 minutes"
                elif tagged_job_id:
                    # Check if associated job is already terminal
                    job_record = get_job(jobs_table, tagged_job_id)
                    terminal_vals = {s.value for s in TERMINAL_JOB_STATUSES}
                    if not job_record or job_record.get("status") in terminal_vals:
                        should_terminate = True
                        reason = f"Associated job {tagged_job_id} is already terminal or missing"

                if should_terminate:
                    logger.warning(f"Watchdog terminating orphan instance {inst_id}: {reason}")
                    terminate_ec2_instance(region, inst_id)

    except Exception as e:
        logger.warning(f"Error checking orphan EC2 instances: {e}")

    # ──────────────────────────────────────────────
    # 3. Clean Up Abandoned Datasets
    # ──────────────────────────────────────────────
    try:
        ds_table = resource.Table(datasets_table)
        s3 = get_s3_client()
        scan_resp = ds_table.scan(
            FilterExpression="#st = :pending",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={":pending": "PENDING_UPLOAD"},
        )
        for ds in scan_resp.get("Items", []):
            created_dt = parse_iso(ds.get("created_at"))
            if created_dt and (now - created_dt) > timedelta(hours=1):
                ds_id = ds["dataset_id"]
                s3_key = ds.get("s3_key")
                s3_exists = False
                if s3_key:
                    try:
                        s3.head_object(Bucket=data_bucket, Key=s3_key)
                        s3_exists = True
                    except Exception:
                        s3_exists = False
                if not s3_exists:
                    logger.info(
                        f"Deleting abandoned PENDING_UPLOAD dataset {ds_id} (created > 1 hr ago, no S3 object)."
                    )
                    ds_table.delete_item(Key={"dataset_id": ds_id})
    except Exception as e:
        logger.warning(f"Error cleaning up abandoned datasets: {e}")

    # ──────────────────────────────────────────────
    # 4. Reconcile Capacity Slots
    # ──────────────────────────────────────────────
    try:
        current_in_use = get_capacity_in_use(jobs_table)
        # Re-fetch active jobs for precise count
        actual_active = 0
        terminal_vals = {s.value for s in TERMINAL_JOB_STATUSES}
        for status_val in active_statuses:
            resp = table.query(
                IndexName="status-updated-index",
                KeyConditionExpression="#st = :st",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={":st": status_val},
            )
            for j in resp.get("Items", []):
                if not j.get("slot_released", False) and j.get("status") not in terminal_vals:
                    actual_active += 1

        if current_in_use != actual_active:
            logger.warning(
                f"Capacity drift detected! In-use in DynamoDB: {current_in_use}, actual active jobs: {actual_active}. Overwriting."
            )
            set_capacity_in_use(jobs_table, actual_active)
        else:
            logger.info(f"Capacity slots reconciled successfully. Current in-use: {actual_active}")

    except Exception as e:
        logger.warning(f"Error during capacity slots reconciliation: {e}")

    return {"statusCode": 200, "message": "Watchdog run completed."}
