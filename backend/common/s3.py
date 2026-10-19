"""S3 storage access layer, pre-signed URL generation, and artifact helpers."""

import json
import os
from typing import Any

import boto3
from botocore.config import Config

from common.logging import get_logger

logger = get_logger("s3")


def get_s3_client() -> Any:
    """Create or return an S3 client, supporting local emulator via S3_ENDPOINT_URL."""
    endpoint_url = os.getenv("S3_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL")
    # Use path-style addressing for local emulator compatibility (Minio/Localstack)
    s3_config = Config(s3={"addressing_style": "path"}) if endpoint_url else None
    return boto3.client("s3", endpoint_url=endpoint_url, config=s3_config)


def generate_presigned_upload(
    bucket_name: str,
    key: str,
    max_size_bytes: int = 100 * 1024 * 1024,  # 100 MB default cap
    expires_in: int = 900,  # 15 minutes
) -> dict[str, Any]:
    """Generate a pre-signed S3 POST for uploading a dataset file directly from browser."""
    client = get_s3_client()
    conditions = [
        ["content-length-range", 1, max_size_bytes],
        {"key": key},
    ]
    post_data = client.generate_presigned_post(
        Bucket=bucket_name,
        Key=key,
        Conditions=conditions,
        ExpiresIn=expires_in,
    )
    return {
        "url": post_data["url"],
        "fields": post_data["fields"],
        "expires_in": expires_in,
    }


def generate_presigned_download(
    bucket_name: str,
    key: str,
    expires_in: int = 900,
    filename: str | None = None,
) -> str:
    """Generate a pre-signed GET URL for downloading an artifact or dataset."""
    client = get_s3_client()
    params = {"Bucket": bucket_name, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

    return client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires_in,
    )


def list_artifacts(bucket_name: str, prefix: str) -> list[dict[str, Any]]:
    """List all artifacts in an S3 prefix."""
    client = get_s3_client()
    prefix = prefix.rstrip("/") + "/"
    paginator = client.get_paginator("list_objects_v2")

    files: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        for item in page.get("Contents", []):
            key = item["Key"]
            rel_name = key[len(prefix) :]
            if rel_name:
                files.append(
                    {
                        "name": rel_name,
                        "key": key,
                        "size": item["Size"],
                        "last_modified": item["LastModified"].isoformat(),
                    }
                )
    return files


def delete_prefix(bucket_name: str, prefix: str) -> int:
    """Delete all objects under a given S3 prefix."""
    client = get_s3_client()
    prefix = prefix.rstrip("/") + "/"
    paginator = client.get_paginator("list_objects_v2")

    deleted_count = 0
    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
        if objects:
            client.delete_objects(
                Bucket=bucket_name,
                Delete={"Objects": objects, "Quiet": True},
            )
            deleted_count += len(objects)

    return deleted_count


def put_json(bucket_name: str, key: str, data: Any) -> None:
    """Serialize and write a Python object as JSON to S3."""
    client = get_s3_client()
    client.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=json.dumps(data, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def get_json(bucket_name: str, key: str) -> Any:
    """Read and parse a JSON object from S3."""
    client = get_s3_client()
    resp = client.get_object(Bucket=bucket_name, Key=key)
    body = resp["Body"].read().decode("utf-8")
    return json.loads(body)
