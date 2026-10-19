"""S3 ObjectCreated Lambda handler for dataset profiling.

Invoked asynchronously when a user uploads data.csv to S3 datasets/ prefix.
"""

import os
import re
import urllib.parse
from datetime import UTC, datetime
from typing import Any

from common.ddb import get_ddb_resource, to_dynamo_safe
from common.logging import get_logger
from common.s3 import get_s3_client
from dataset_profiler.profiler import profile_csv_content

logger = get_logger("dataset_profiler")

DATASET_KEY_REGEX = re.compile(r"^datasets/([^/]+)/([^/]+)/data\.csv$")


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Process S3 ObjectCreated records and profile tabular datasets."""
    datasets_table = os.getenv("DATASETS_TABLE", "cloudtrain-dev-datasets")
    s3_client = get_s3_client()
    resource = get_ddb_resource()
    table = resource.Table(datasets_table)

    processed = 0

    for record in event.get("Records", []):
        s3_info = record.get("s3", {})
        bucket_name = s3_info.get("bucket", {}).get("name")
        raw_key = s3_info.get("object", {}).get("key", "")
        key = urllib.parse.unquote_plus(raw_key)

        match = DATASET_KEY_REGEX.match(key)
        if not match:
            logger.info(f"Skipping non-dataset key: {key}")
            continue

        user_id, dataset_id = match.group(1), match.group(2)
        logger.info(f"Profiling dataset {dataset_id} for user {user_id} from s3://{bucket_name}/{key}")

        # Update status to PROFILING
        try:
            table.update_item(
                Key={"dataset_id": dataset_id},
                UpdateExpression="SET #st = :prof, updated_at = :ts",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={":prof": "PROFILING", ":ts": now_iso()},
            )
        except Exception as e:
            logger.warning(f"Failed to set PROFILING status on {dataset_id}: {e}")

        # Fetch object content
        try:
            resp = s3_client.get_object(Bucket=bucket_name, Key=key)
            csv_bytes = resp["Body"].read()
            content_length = resp.get("ContentLength", len(csv_bytes))
        except Exception as e:
            logger.error(f"Failed to read S3 object s3://{bucket_name}/{key}: {e}")
            table.update_item(
                Key={"dataset_id": dataset_id},
                UpdateExpression="SET #st = :inv, errors = :errs, updated_at = :ts",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":inv": "INVALID",
                    ":errs": [f"Could not read uploaded S3 object: {e}"],
                    ":ts": now_iso(),
                },
            )
            continue

        # Profile content
        profile, errors = profile_csv_content(csv_bytes)

        if errors:
            logger.warning(f"Dataset {dataset_id} is INVALID: {errors}")
            table.update_item(
                Key={"dataset_id": dataset_id},
                UpdateExpression="SET #st = :inv, errors = :errs, size_bytes = :sb, updated_at = :ts",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":inv": "INVALID",
                    ":errs": errors,
                    ":sb": content_length,
                    ":ts": now_iso(),
                },
            )
        else:
            logger.info(f"Dataset {dataset_id} is READY ({profile['row_count']} rows, {profile['column_count']} cols)")
            table.update_item(
                Key={"dataset_id": dataset_id},
                UpdateExpression="SET #st = :rdy, profile = :prof, size_bytes = :sb, updated_at = :ts",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={
                    ":rdy": "READY",
                    ":prof": to_dynamo_safe(profile),
                    ":sb": content_length,
                    ":ts": now_iso(),
                },
            )

        processed += 1

    return {"statusCode": 200, "processed": processed}
