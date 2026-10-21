"""CloudTrain API Gateway HTTP API v2.0 handler.

Implements all REST endpoints for user profiles, model registry,
dataset management, job submission, control, logs, and artifacts.
"""

import base64
import json
import os
import re
import subprocess
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import boto3

from common.ddb import (
    count_user_active_jobs,
    count_user_datasets,
    create_dataset,
    create_job,
    from_dynamo_safe,
    get_dataset,
    get_ddb_resource,
    get_job,
    release_capacity_slot_transaction,
)
from common.errors import (
    CloudTrainError,
    ValidationError,
)
from common.logging import get_logger
from common.registry import load_registry
from common.s3 import (
    delete_prefix,
    generate_presigned_download,
    generate_presigned_upload,
    get_s3_client,
    list_artifacts,
)
from common.schemas import validate_and_resolve_job_config
from common.sqs import enqueue_job
from common.states import TERMINAL_JOB_STATUSES, JobStatus

logger = get_logger("api")


def now_iso() -> str:
    """Return current UTC time in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


def make_cors_headers() -> dict[str, str]:
    """Generate standard CORS headers for HTTP responses."""
    origin = os.getenv("CORS_ALLOW_ORIGIN", "*")
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "Authorization, Content-Type, x-user-sub, x-user-email, sub, *",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Max-Age": "3000",
    }


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that converts Decimal to int or float."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def make_response(status_code: int, body: Any = None) -> dict[str, Any]:
    """Format an HTTP API v2.0 response."""
    headers = make_cors_headers()
    resp: dict[str, Any] = {
        "statusCode": status_code,
        "headers": headers,
    }
    if body is not None:
        resp["body"] = json.dumps(body, cls=DecimalEncoder) if not isinstance(body, str) else body
    return resp


def make_error_response(
    status_code: int, code: str, message: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Format a consistent error envelope."""
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details:
        payload["error"]["details"] = details
    return make_response(status_code, payload)


def extract_user_id(event: dict[str, Any]) -> tuple[str, str]:
    """Extract (user_id, email) from API Gateway HTTP API v2.0 event or local bypass."""
    env = os.getenv("ENV", "dev")
    bypass = os.getenv("LOCAL_AUTH_BYPASS", "0")

    if bypass == "1":
        if env != "local":
            raise RuntimeError(f"LOCAL_AUTH_BYPASS is prohibited when ENV={env}. Only allowed when ENV=local.")
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        user_id = headers.get("x-user-sub") or headers.get("sub") or "local-dev-user"
        email = headers.get("x-user-email") or "local-dev@cloudtrain.example.com"
        return user_id, email

    # Standard Cognito JWT Authorizer claims in HTTP API v2.0
    req_ctx = event.get("requestContext", {})
    authorizer = req_ctx.get("authorizer", {})
    jwt_claims = authorizer.get("jwt", {}).get("claims", {})

    user_id = jwt_claims.get("sub")
    email = jwt_claims.get("email", "")

    if not user_id:
        # Check standard headers for fallback authorizers
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        auth_header = headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            # If sub is not in authorizer, caller is unauthorized
            pass

    return user_id or "", email


def encode_cursor(last_key: dict[str, Any] | None) -> str | None:
    """Encode DynamoDB LastEvaluatedKey to a URL-safe base64 string."""
    if not last_key:
        return None
    raw = json.dumps(last_key)
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    """Decode a base64 pagination cursor into DynamoDB LastEvaluatedKey."""
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        return json.loads(raw)
    except Exception:
        return None


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Main entrypoint for API Gateway HTTP API Lambda."""
    http_method = event.get("requestContext", {}).get("http", {}).get("method", "").upper()
    raw_path = event.get("rawPath") or event.get("requestContext", {}).get("http", {}).get("path", "")
    # Normalize path: strip trailing slash except for root
    path = raw_path.rstrip("/") if len(raw_path) > 1 else raw_path

    # Handle CORS preflight
    if http_method == "OPTIONS":
        return make_response(204)

    # Auth extraction
    try:
        user_id, user_email = extract_user_id(event)
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return make_error_response(500, "AUTH_CONFIGURATION_ERROR", str(e))

    if not user_id:
        return make_error_response(401, "UNAUTHORIZED", "Missing or invalid authorization token.")

    # Parse query parameters and JSON body
    query_params = event.get("queryStringParameters") or {}
    body_str = event.get("body")
    body: dict[str, Any] = {}
    if body_str:
        if event.get("isBase64Encoded"):
            body_str = base64.b64decode(body_str).decode("utf-8")
        try:
            body = json.loads(body_str)
        except json.JSONDecodeError:
            return make_error_response(400, "BAD_REQUEST", "Invalid JSON request body.")

    # Config env vars
    datasets_table = os.getenv("DATASETS_TABLE", "cloudtrain-dev-datasets")
    jobs_table = os.getenv("JOBS_TABLE", "cloudtrain-dev-jobs")
    data_bucket = os.getenv("DATA_BUCKET", "cloudtrain-dev-data")
    jobs_queue_url = os.getenv("JOBS_QUEUE_URL", "")
    max_datasets = int(os.getenv("MAX_DATASETS_PER_USER", "10"))
    max_active_jobs = int(os.getenv("MAX_ACTIVE_JOBS_PER_USER", "3"))
    max_dataset_bytes = int(os.getenv("MAX_DATASET_BYTES", str(100 * 1024 * 1024)))
    training_log_group = os.getenv("TRAINING_LOG_GROUP", "/cloudtrain/dev/training")

    try:
        # ──────────────────────────────────────────────
        # Routes: /me
        # ──────────────────────────────────────────────
        if http_method == "GET" and path == "/me":
            ds_used = count_user_datasets(datasets_table, user_id)
            active_jobs = count_user_active_jobs(jobs_table, user_id)
            return make_response(
                200,
                {
                    "user_id": user_id,
                    "email": user_email,
                    "quotas": {
                        "datasets_used": ds_used,
                        "datasets_max": max_datasets,
                        "active_jobs": active_jobs,
                        "active_jobs_max": max_active_jobs,
                    },
                },
            )

        # ──────────────────────────────────────────────
        # Routes: /models
        # ──────────────────────────────────────────────
        if http_method == "GET" and path == "/models":
            registry = load_registry()
            return make_response(200, registry)

        # ──────────────────────────────────────────────
        # Routes: /datasets
        # ──────────────────────────────────────────────
        if http_method == "POST" and path == "/datasets":
            req_filename = (body.get("filename") or body.get("name") or "").strip()
            display_name = (body.get("name") or body.get("filename") or "").strip()

            if not req_filename.lower().endswith(".csv"):
                if not display_name.lower().endswith(".csv"):
                    return make_error_response(400, "INVALID_FILENAME", "Dataset filename must end with .csv")
                req_filename = display_name

            if len(display_name) > 255:
                return make_error_response(400, "INVALID_FILENAME", "Dataset name too long (max 255 chars)")

            ds_used = count_user_datasets(datasets_table, user_id)
            if ds_used >= max_datasets:
                return make_error_response(
                    429,
                    "DATASET_LIMIT",
                    f"User has reached the maximum allowed datasets limit of {max_datasets}.",
                )

            dataset_id = str(uuid.uuid4())
            s3_key = f"datasets/{user_id}/{dataset_id}/data.csv"

            upload_data = generate_presigned_upload(
                bucket_name=data_bucket,
                key=s3_key,
                max_size_bytes=max_dataset_bytes,
                expires_in=900,
            )

            record = {
                "dataset_id": dataset_id,
                "user_id": user_id,
                "name": display_name,
                "filename": req_filename,
                "s3_key": s3_key,
                "size_bytes": 0,
                "status": "PENDING_UPLOAD",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            create_dataset(datasets_table, record)

            return make_response(
                201,
                {
                    "dataset_id": dataset_id,
                    "url": upload_data["url"],
                    "fields": upload_data["fields"],
                    "upload": {
                        "url": upload_data["url"],
                        "fields": upload_data["fields"],
                    },
                    "expires_in": 900,
                },
            )

        if http_method == "GET" and path == "/datasets":
            limit = min(int(query_params.get("limit", 20)), 100)
            cursor = query_params.get("cursor")
            exclusive_start_key = decode_cursor(cursor)

            resource = get_ddb_resource()
            table = resource.Table(datasets_table)
            query_kwargs: dict[str, Any] = {
                "IndexName": "user-created-index",
                "KeyConditionExpression": "user_id = :uid",
                "ExpressionAttributeValues": {":uid": user_id},
                "ScanIndexForward": False,
                "Limit": limit,
            }
            if exclusive_start_key:
                query_kwargs["ExclusiveStartKey"] = exclusive_start_key

            resp = table.query(**query_kwargs)
            items = [from_dynamo_safe(item) for item in resp.get("Items", [])]
            next_cursor = encode_cursor(resp.get("LastEvaluatedKey"))
            return make_response(200, {"items": items, "next_cursor": next_cursor})

        ds_match = re.match(r"^/datasets/([a-zA-Z0-9_-]+)$", path)
        if ds_match:
            dataset_id = ds_match.group(1)
            ds = get_dataset(datasets_table, dataset_id)
            if not ds or ds.get("user_id") != user_id:
                return make_error_response(404, "NOT_FOUND", "Dataset not found.")

            if http_method == "GET":
                return make_response(200, ds)

            if http_method == "DELETE":
                # Check if any active job references this dataset
                resource = get_ddb_resource()
                jobs_tbl = resource.Table(jobs_table)
                j_resp = jobs_tbl.query(
                    IndexName="user-created-index",
                    KeyConditionExpression="user_id = :uid",
                    ExpressionAttributeValues={":uid": user_id},
                )
                terminal_vals = {s.value for s in TERMINAL_JOB_STATUSES}
                for j in j_resp.get("Items", []):
                    if j.get("dataset_id") == dataset_id and j.get("status") not in terminal_vals:
                        return make_error_response(
                            409,
                            "DATASET_IN_USE",
                            "Cannot delete dataset currently in use by an active training job.",
                        )

                # Delete S3 object
                s3 = get_s3_client()
                try:
                    s3.delete_object(Bucket=data_bucket, Key=ds["s3_key"])
                except Exception as e:
                    logger.warning(f"Error deleting S3 key {ds.get('s3_key')}: {e}")

                # Delete DynamoDB record
                table = resource.Table(datasets_table)
                table.delete_item(Key={"dataset_id": dataset_id})
                return make_response(204)

        # ──────────────────────────────────────────────
        # Routes: /jobs
        # ──────────────────────────────────────────────
        if http_method == "POST" and path == "/jobs":
            target_ds_id = body.get("dataset_id")
            if not target_ds_id:
                return make_error_response(
                    400,
                    "VALIDATION_FAILED",
                    "Missing dataset_id",
                    {"fields": [{"path": "dataset_id", "message": "Required"}]},
                )

            ds = get_dataset(datasets_table, target_ds_id)
            if not ds or ds.get("user_id") != user_id:
                return make_error_response(404, "NOT_FOUND", "Dataset not found.")

            if ds.get("status") != "READY":
                return make_error_response(
                    409,
                    "DATASET_NOT_READY",
                    f"Dataset is not ready for training (current status: {ds.get('status')}).",
                )

            # Check active jobs quota
            active_jobs = count_user_active_jobs(jobs_table, user_id)
            if active_jobs >= max_active_jobs:
                return make_error_response(
                    429,
                    "TOO_MANY_ACTIVE_JOBS",
                    f"Active jobs limit reached ({max_active_jobs}). Wait for existing jobs to finish.",
                )

            profile = ds.get("profile", {})
            try:
                resolved_config = validate_and_resolve_job_config(body, profile)
            except ValidationError as val_err:
                return make_error_response(
                    400,
                    "VALIDATION_FAILED",
                    val_err.message,
                    {"fields": val_err.field_errors},
                )

            job_id = str(uuid.uuid4())
            artifact_prefix = f"jobs/{user_id}/{job_id}/artifacts/"
            config_s3_key = f"jobs/{user_id}/{job_id}/config.json"

            # Write config to S3
            s3 = get_s3_client()
            s3.put_object(
                Bucket=data_bucket,
                Key=config_s3_key,
                Body=json.dumps(resolved_config, indent=2),
                ContentType="application/json",
                ServerSideEncryption="AES256",
            )

            job_record = {
                "job_id": job_id,
                "user_id": user_id,
                "name": resolved_config.get("name", "Training Job"),
                "dataset_id": target_ds_id,
                "status": JobStatus.QUEUED.value,
                "stage": "QUEUED",
                "progress": 0,
                "config": resolved_config,
                "config_version": 1,
                "artifact_prefix": artifact_prefix,
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "cancel_requested": False,
                "slot_released": False,
            }
            create_job(jobs_table, job_record)

            # Dispatch onto SQS jobs queue
            if jobs_queue_url:
                enqueue_job(jobs_queue_url, job_id, user_id)

            return make_response(202, {"job_id": job_id, "status": "QUEUED"})

        if http_method == "GET" and path == "/jobs":
            limit = min(int(query_params.get("limit", 20)), 100)
            cursor = query_params.get("cursor")
            status_filter = query_params.get("status")
            exclusive_start_key = decode_cursor(cursor)

            resource = get_ddb_resource()
            table = resource.Table(jobs_table)
            query_kwargs = {
                "IndexName": "user-created-index",
                "KeyConditionExpression": "user_id = :uid",
                "ExpressionAttributeValues": {":uid": user_id},
                "ScanIndexForward": False,
                "Limit": limit,
            }
            if status_filter:
                query_kwargs["FilterExpression"] = "#st = :st"
                query_kwargs["ExpressionAttributeNames"] = {"#st": "status"}
                query_kwargs["ExpressionAttributeValues"][":st"] = status_filter
            if exclusive_start_key:
                query_kwargs["ExclusiveStartKey"] = exclusive_start_key

            resp = table.query(**query_kwargs)
            items = [from_dynamo_safe(item) for item in resp.get("Items", [])]
            next_cursor = encode_cursor(resp.get("LastEvaluatedKey"))
            return make_response(200, {"items": items, "next_cursor": next_cursor})

        # Match job-specific subpaths
        job_match = re.match(r"^/jobs/([a-zA-Z0-9_-]+)(?:/(cancel|logs|artifacts|results))?$", path)
        if job_match:
            job_id = job_match.group(1)
            action = job_match.group(2)

            job = get_job(jobs_table, job_id)
            if not job or job.get("user_id") != user_id:
                return make_error_response(404, "NOT_FOUND", "Job not found.")

            current_status = job.get("status", "")

            # 1. GET /jobs/{id}
            if not action and http_method == "GET":
                return make_response(200, job)

            # 2. DELETE /jobs/{id}
            if not action and http_method == "DELETE":
                terminal_vals = {s.value for s in TERMINAL_JOB_STATUSES}
                if current_status not in terminal_vals:
                    return make_error_response(
                        409,
                        "JOB_ACTIVE",
                        f"Cannot delete active job (status: {current_status}). Cancel or wait for completion.",
                    )

                # Delete all S3 objects under jobs/{user_id}/{job_id}/
                job_prefix = f"jobs/{user_id}/{job_id}/"
                delete_prefix(data_bucket, job_prefix)

                # Delete DynamoDB record
                resource = get_ddb_resource()
                table = resource.Table(jobs_table)
                table.delete_item(Key={"job_id": job_id})
                return make_response(204)

            # 3. POST /jobs/{id}/cancel
            if action == "cancel" and http_method == "POST":
                terminal_vals = {s.value for s in TERMINAL_JOB_STATUSES}
                if current_status in terminal_vals:
                    return make_error_response(
                        409,
                        "ALREADY_FINISHED",
                        f"Job is already finished (status: {current_status}).",
                    )

                now_ts = now_iso()
                resource = get_ddb_resource()
                table = resource.Table(jobs_table)

                if current_status == JobStatus.QUEUED.value:
                    # Cancel in queue; launcher will skip
                    table.update_item(
                        Key={"job_id": job_id},
                        UpdateExpression="SET #st = :canc, #sg = :canc, finished_at = :ts, updated_at = :ts",
                        ExpressionAttributeNames={"#st": "status", "#sg": "stage"},
                        ExpressionAttributeValues={":canc": JobStatus.CANCELLED.value, ":ts": now_ts},
                    )
                else:
                    # PROVISIONING, RUNNING, UPLOADING
                    table.update_item(
                        Key={"job_id": job_id},
                        UpdateExpression="SET cancel_requested = :true, #st = :canc, #sg = :canc, finished_at = :ts, updated_at = :ts",
                        ExpressionAttributeNames={"#st": "status", "#sg": "stage"},
                        ExpressionAttributeValues={
                            ":true": True,
                            ":canc": JobStatus.CANCELLED.value,
                            ":ts": now_ts,
                        },
                    )
                    # If instance_id present, terminate EC2 instance
                    instance_id = job.get("instance_id")
                    if instance_id:
                        try:
                            from job_launcher.compute import get_compute_backend

                            get_compute_backend().terminate(instance_id)
                        except Exception as e:
                            logger.warning(f"Failed to terminate instance {instance_id}: {e}")

                    # Release capacity slot
                    release_capacity_slot_transaction(jobs_table, job_id)

                return make_response(202, {"job_id": job_id, "status": "CANCELLED"})

            # 4. GET /jobs/{id}/logs
            if action == "logs" and http_method == "GET":
                if os.getenv("ENV") == "local" and job.get("instance_id", "").startswith("local-"):
                    try:
                        output = subprocess.run(
                            ["docker", "logs", "--tail", "1000", f"trainer-{job_id}"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                            check=True,
                        )
                        return make_response(
                            200,
                            {
                                "lines": [
                                    {"ts": 0, "text": line} for line in (output.stdout + output.stderr).splitlines()
                                ],
                                "next": None,
                                "source": "docker",
                            },
                        )
                    except (OSError, subprocess.SubprocessError):
                        pass  # Finished containers are removed; use archived S3 logs below.
                next_token = query_params.get("next")
                logs_client = boto3.client("logs")
                lines: list[dict[str, Any]] = []
                new_next = None
                source = "none"

                # Try CloudWatch Logs
                try:
                    kwargs: dict[str, Any] = {
                        "logGroupName": training_log_group,
                        "logStreamName": job_id,
                        "startFromHead": True,
                    }
                    if next_token:
                        kwargs["nextToken"] = next_token
                    cw_resp = logs_client.get_log_events(**kwargs)
                    for ev in cw_resp.get("events", []):
                        lines.append({"ts": ev["timestamp"], "text": ev["message"]})
                    new_next = cw_resp.get("nextForwardToken")
                    source = "cloudwatch"
                except Exception:
                    # Fallback to S3 logs.txt
                    try:
                        s3 = get_s3_client()
                        logs_obj = s3.get_object(Bucket=data_bucket, Key=f"jobs/{user_id}/{job_id}/logs.txt")
                        content = logs_obj["Body"].read().decode("utf-8")
                        lines = [{"ts": 0, "text": line} for line in content.splitlines()]
                        source = "s3"
                    except Exception:
                        lines = []
                        source = "none"

                return make_response(200, {"lines": lines, "next": new_next, "source": source})

            # 5. GET /jobs/{id}/artifacts
            if action == "artifacts" and http_method == "GET":
                if current_status != JobStatus.SUCCEEDED.value:
                    return make_error_response(
                        409,
                        "JOB_NOT_SUCCEEDED",
                        f"Artifacts are only available for SUCCEEDED jobs (current: {current_status}).",
                    )

                prefix = f"jobs/{user_id}/{job_id}/artifacts/"
                items = list_artifacts(data_bucket, prefix)
                files = []
                for item in items:
                    dl_url = generate_presigned_download(
                        bucket_name=data_bucket,
                        key=item["key"],
                        expires_in=900,
                        filename=item["name"],
                    )
                    files.append({"name": item["name"], "size": item["size"], "url": dl_url})

                return make_response(200, {"files": files})

            # 6. GET /jobs/{id}/results
            if action == "results" and http_method == "GET":
                if current_status != JobStatus.SUCCEEDED.value:
                    return make_error_response(
                        409,
                        "JOB_NOT_SUCCEEDED",
                        f"Results are only available for SUCCEEDED jobs (current: {current_status}).",
                    )

                s3 = get_s3_client()
                metrics = {}
                feature_importance = {}
                try:
                    m_obj = s3.get_object(Bucket=data_bucket, Key=f"jobs/{user_id}/{job_id}/artifacts/metrics.json")
                    metrics = json.loads(m_obj["Body"].read().decode("utf-8"))
                except Exception as e:
                    logger.warning(f"Could not load metrics.json for {job_id}: {e}")

                try:
                    fi_obj = s3.get_object(
                        Bucket=data_bucket, Key=f"jobs/{user_id}/{job_id}/artifacts/feature_importance.json"
                    )
                    feature_importance = json.loads(fi_obj["Body"].read().decode("utf-8"))
                except Exception as e:
                    logger.warning(f"Could not load feature_importance.json for {job_id}: {e}")

                return make_response(200, {"metrics": metrics, "feature_importance": feature_importance})

        return make_error_response(404, "NOT_FOUND", f"Route {http_method} {path} not found.")

    except CloudTrainError as cte:
        logger.error(f"CloudTrain application error: {cte}")
        return make_error_response(cte.status_code, cte.code, cte.message, cte.details)
    except Exception as exc:
        logger.exception(f"Unhandled error processing {http_method} {path}: {exc}")
        return make_error_response(500, "INTERNAL_ERROR", "An internal error occurred.")
