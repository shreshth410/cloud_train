"""DynamoDB access layer, atomic state updates, and capacity slot management."""

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from common.logging import get_logger
from common.states import (
    TERMINAL_JOB_STATUSES,
    JobStatus,
)

logger = get_logger("ddb")


def to_dynamo_safe(obj: Any) -> Any:
    """Recursively convert float to Decimal for DynamoDB storage."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: to_dynamo_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_dynamo_safe(v) for v in obj]
    return obj


def from_dynamo_safe(obj: Any) -> Any:
    """Recursively convert Decimal to float or int."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: from_dynamo_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [from_dynamo_safe(v) for v in obj]
    return obj


def get_ddb_client() -> Any:
    """Create or return a DynamoDB client, supporting local emulator via DYNAMODB_ENDPOINT_URL."""
    endpoint_url = os.getenv("DYNAMODB_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL")
    return boto3.client("dynamodb", endpoint_url=endpoint_url)


def get_ddb_resource() -> Any:
    """Create or return a DynamoDB resource."""
    endpoint_url = os.getenv("DYNAMODB_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL")
    return boto3.resource("dynamodb", endpoint_url=endpoint_url)


def now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(UTC).isoformat()


# ──────────────────────────────────────────────
# Capacity Management (Section 8.4)
# ──────────────────────────────────────────────
CAPACITY_ITEM_PK = "__capacity__"


def acquire_capacity_slot(table_name: str, max_concurrent: int = 2) -> bool:
    """Attempt to acquire a capacity slot atomically.

    Returns True if slot acquired, False if capacity full.
    """
    client = get_ddb_client()
    try:
        client.update_item(
            TableName=table_name,
            Key={"job_id": {"S": CAPACITY_ITEM_PK}},
            UpdateExpression="ADD in_use :one",
            ConditionExpression="attribute_not_exists(in_use) OR in_use < :max",
            ExpressionAttributeValues={
                ":one": {"N": "1"},
                ":max": {"N": str(max_concurrent)},
            },
        )
        logger.info(f"Capacity slot acquired. Max concurrent: {max_concurrent}")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.info("Capacity full. Could not acquire slot.")
            return False
        logger.error(f"Error acquiring capacity slot: {e}")
        raise


def release_capacity_slot(table_name: str) -> bool:
    """Directly decrement the in_use counter if > 0."""
    client = get_ddb_client()
    try:
        client.update_item(
            TableName=table_name,
            Key={"job_id": {"S": CAPACITY_ITEM_PK}},
            UpdateExpression="ADD in_use :minus_one",
            ConditionExpression="attribute_exists(in_use) AND in_use > :zero",
            ExpressionAttributeValues={
                ":minus_one": {"N": "-1"},
                ":zero": {"N": "0"},
            },
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise


def release_capacity_slot_transaction(table_name: str, job_id: str) -> bool:
    """Release a capacity slot exactly once for a job via a DynamoDB transaction."""
    client = get_ddb_client()
    try:
        client.transact_write_items(
            TransactItems=[
                {
                    "Update": {
                        "TableName": table_name,
                        "Key": {"job_id": {"S": job_id}},
                        "UpdateExpression": "SET slot_released = :true, updated_at = :ts",
                        "ConditionExpression": "attribute_not_exists(slot_released) OR slot_released = :false",
                        "ExpressionAttributeValues": {
                            ":true": {"BOOL": True},
                            ":false": {"BOOL": False},
                            ":ts": {"S": now_iso()},
                        },
                    }
                },
                {
                    "Update": {
                        "TableName": table_name,
                        "Key": {"job_id": {"S": CAPACITY_ITEM_PK}},
                        "UpdateExpression": "ADD in_use :minus_one",
                        "ConditionExpression": "attribute_exists(in_use) AND in_use > :zero",
                        "ExpressionAttributeValues": {
                            ":minus_one": {"N": "-1"},
                            ":zero": {"N": "0"},
                        },
                    }
                },
            ]
        )
        logger.info(f"Released capacity slot for job {job_id}")
        return True
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("TransactionCanceledException", "ConditionalCheckFailedException"):
            logger.info(f"Slot for job {job_id} already released or counter was 0.")
            return False
        raise


def get_capacity_in_use(table_name: str) -> int:
    """Get the current in_use capacity count."""
    client = get_ddb_client()
    resp = client.get_item(
        TableName=table_name,
        Key={"job_id": {"S": CAPACITY_ITEM_PK}},
    )
    item = resp.get("Item")
    if not item or "in_use" not in item:
        return 0
    return int(item["in_use"]["N"])


def set_capacity_in_use(table_name: str, value: int) -> None:
    """Force set the in_use capacity counter (used by watchdog reconcile)."""
    client = get_ddb_client()
    client.update_item(
        TableName=table_name,
        Key={"job_id": {"S": CAPACITY_ITEM_PK}},
        UpdateExpression="SET in_use = :val",
        ExpressionAttributeValues={":val": {"N": str(max(0, value))}},
    )


# ──────────────────────────────────────────────
# Job Record Helpers
# ──────────────────────────────────────────────


def get_job(table_name: str, job_id: str) -> dict[str, Any] | None:
    """Fetch job item converted from DynamoDB attribute format."""
    resource = get_ddb_resource()
    table = resource.Table(table_name)
    resp = table.get_item(Key={"job_id": job_id})
    item = resp.get("Item")
    return from_dynamo_safe(item) if item is not None else None


def create_job(table_name: str, job_item: dict[str, Any]) -> None:
    """Put a new job item into DynamoDB."""
    resource = get_ddb_resource()
    table = resource.Table(table_name)
    now = now_iso()
    job_item.setdefault("created_at", now)
    job_item.setdefault("updated_at", now)
    job_item.setdefault("progress", 0)
    job_item.setdefault("slot_released", False)
    safe_item = to_dynamo_safe(job_item)
    table.put_item(Item=safe_item)


def apply_status_event(
    table_name: str,
    event: dict[str, Any],
) -> bool:
    """Apply a status event to a job atomically with sequence and rank checking.

    Condition:
    attribute_exists(job_id)
    AND (attribute_not_exists(last_seq) OR last_seq < :seq)
    AND rank(current_status) <= rank(:new_status)
    AND current_status NOT IN (SUCCEEDED, FAILED, CANCELLED, TIMED_OUT)
    """
    job_id = event["job_id"]
    seq = event["seq"]
    new_status = event["status"]
    stage = event["stage"]
    progress = event["progress"]
    ts = event.get("ts", now_iso())
    payload = event.get("payload", {})

    update_expr_parts = [
        "#st = :status",
        "#sg = :stage",
        "#pr = :progress",
        "#ls = :seq",
        "#lea = :ts",
        "#ua = :ts",
    ]
    expr_names = {
        "#st": "status",
        "#sg": "stage",
        "#pr": "progress",
        "#ls": "last_seq",
        "#lea": "last_event_at",
        "#ua": "updated_at",
    }
    expr_values: dict[str, Any] = {
        ":status": {"S": new_status},
        ":stage": {"S": stage},
        ":progress": {"N": str(progress)},
        ":seq": {"N": str(seq)},
        ":ts": {"S": ts},
        ":succeeded": {"S": JobStatus.SUCCEEDED.value},
        ":failed": {"S": JobStatus.FAILED.value},
        ":cancelled": {"S": JobStatus.CANCELLED.value},
        ":timed_out": {"S": JobStatus.TIMED_OUT.value},
    }

    if "metrics_summary" in payload:
        # Flatten simple key-values for metrics_summary
        metrics_m: dict[str, Any] = {}
        for k, v in payload["metrics_summary"].items():
            if isinstance(v, (int, float)):
                metrics_m[k] = {"N": str(v)}
            else:
                metrics_m[k] = {"S": str(v)}
        update_expr_parts.append("#ms = :ms")
        expr_names["#ms"] = "metrics_summary"
        expr_values[":ms"] = {"M": metrics_m}

    if "error" in payload:
        err = payload["error"]
        update_expr_parts.append("#err = :err")
        expr_names["#err"] = "error"
        expr_values[":err"] = {
            "M": {
                "code": {"S": str(err.get("code", "UNKNOWN"))},
                "message": {"S": str(err.get("message", ""))},
            }
        }

    if new_status in {s.value for s in TERMINAL_JOB_STATUSES}:
        update_expr_parts.append("#fa = :ts")
        expr_names["#fa"] = "finished_at"

    condition_expr = (
        "attribute_exists(job_id) "
        "AND (attribute_not_exists(last_seq) OR last_seq < :seq) "
        "AND NOT #st IN (:succeeded, :failed, :cancelled, :timed_out)"
    )

    client = get_ddb_client()
    try:
        client.update_item(
            TableName=table_name,
            Key={"job_id": {"S": job_id}},
            UpdateExpression="SET " + ", ".join(update_expr_parts),
            ConditionExpression=condition_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            logger.info(f"Status event {seq} for job {job_id} ignored due to condition check.")
            return False
        raise


# ──────────────────────────────────────────────
# Dataset Record Helpers
# ──────────────────────────────────────────────


def get_dataset(table_name: str, dataset_id: str) -> dict[str, Any] | None:
    """Fetch dataset item by ID."""
    resource = get_ddb_resource()
    table = resource.Table(table_name)
    resp = table.get_item(Key={"dataset_id": dataset_id})
    item = resp.get("Item")
    return from_dynamo_safe(item) if item is not None else None


def create_dataset(table_name: str, dataset_item: dict[str, Any]) -> None:
    """Create a new dataset item."""
    resource = get_ddb_resource()
    table = resource.Table(table_name)
    now = now_iso()
    dataset_item.setdefault("created_at", now)
    dataset_item.setdefault("updated_at", now)
    safe_item = to_dynamo_safe(dataset_item)
    table.put_item(Item=safe_item)


def count_user_active_jobs(table_name: str, user_id: str) -> int:
    """Count non-terminal jobs for a user using user-created-index."""
    resource = get_ddb_resource()
    table = resource.Table(table_name)
    resp = table.query(
        IndexName="user-created-index",
        KeyConditionExpression="user_id = :uid",
        ExpressionAttributeValues={":uid": user_id},
    )
    items = resp.get("Items", [])
    active_count = 0
    terminal_values = {s.value for s in TERMINAL_JOB_STATUSES}
    for item in items:
        if item.get("status") not in terminal_values:
            active_count += 1
    return active_count


def count_user_datasets(table_name: str, user_id: str) -> int:
    """Count datasets created by a user."""
    resource = get_ddb_resource()
    table = resource.Table(table_name)
    resp = table.query(
        IndexName="user-created-index",
        KeyConditionExpression="user_id = :uid",
        ExpressionAttributeValues={":uid": user_id},
    )
    return len(resp.get("Items", []))
