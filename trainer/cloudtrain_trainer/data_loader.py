"""Dataset download, loading, target cleaning, and validation."""

import tempfile
from pathlib import Path
from typing import Any

import boto3
import numpy as np
import pandas as pd


class DataValidationError(Exception):
    """Raised when the dataset fails validation checks."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def load_dataset(
    config: dict[str, Any],
    bucket_name: str | None = None,
    user_id: str | None = None,
    s3_endpoint_url: str | None = None,
    region: str | None = None,
    local_csv_path: str | None = None,
) -> tuple[pd.DataFrame, pd.Series, str]:
    """Load, clean, and validate dataset and resolve task type.

    Returns (X, y, resolved_task).
    """
    target_col = config["target_column"]
    dataset_profile = config.get("dataset_profile", {})
    delimiter = dataset_profile.get("delimiter", ",")
    encoding = dataset_profile.get("encoding", "utf-8")

    if local_csv_path:
        csv_file = local_csv_path
    else:
        dataset_id = config["dataset_id"]
        uid = user_id or config.get("user_id")
        assert bucket_name, "DATA_BUCKET must be provided for S3 dataset download"

        s3 = boto3.client(
            "s3",
            region_name=region or "ap-south-1",
            endpoint_url=s3_endpoint_url,
        )
        s3_key = dataset_profile.get("s3_key") or f"datasets/{uid}/{dataset_id}/data.csv"
        csv_file = str(Path(tempfile.gettempdir()) / f"cloudtrain_{dataset_id}.csv")
        try:
            s3.download_file(bucket_name, s3_key, csv_file)
        except Exception as exc:
            raise DataValidationError(
                "DATASET_DOWNLOAD_FAILED",
                f"Failed to download dataset from s3://{bucket_name}/{s3_key}: {exc}",
            ) from exc

    # Read CSV
    try:
        df = pd.read_csv(csv_file, delimiter=delimiter, encoding=encoding)
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(csv_file, delimiter=delimiter, encoding="latin-1")
        except Exception as exc:
            raise DataValidationError(
                "DATASET_DOWNLOAD_FAILED",
                f"Could not parse CSV file: {exc}",
            ) from exc
    except Exception as exc:
        raise DataValidationError(
            "DATASET_DOWNLOAD_FAILED",
            f"Could not read CSV file: {exc}",
        ) from exc

    if target_col not in df.columns:
        raise DataValidationError(
            "TARGET_MISSING",
            f"Target column '{target_col}' was not found in the dataset.",
        )

    # Drop rows with missing target
    df = df.dropna(subset=[target_col]).copy()

    # Enforce minimum rows
    if len(df) < 20:
        raise DataValidationError(
            "TOO_FEW_ROWS",
            f"Dataset has {len(df)} valid rows after dropping missing targets. Minimum required is 20 rows.",
        )

    # Extract target series
    y_raw = df[target_col]
    X_raw = df.drop(columns=[target_col])

    # Filter to specified feature_columns if provided
    feature_columns = config.get("feature_columns")
    if feature_columns:
        valid_features = [c for c in feature_columns if c in X_raw.columns]
        if not valid_features:
            raise DataValidationError(
                "NO_USABLE_FEATURES",
                "None of the specified feature columns were found in the dataset.",
            )
        X_raw = X_raw[valid_features]

    if X_raw.shape[1] < 1:
        raise DataValidationError(
            "NO_USABLE_FEATURES",
            "Dataset does not contain any usable feature columns.",
        )

    # Task resolution
    task = config.get("task", "auto")
    is_numeric = pd.api.types.is_numeric_dtype(y_raw)
    unique_count = y_raw.nunique()

    resolved_task = ("regression" if is_numeric and unique_count > 20 else "classification") if task == "auto" else task

    # Validate target for task
    if resolved_task == "classification":
        if unique_count < 2:
            raise DataValidationError(
                "TARGET_CONSTANT",
                f"Classification target '{target_col}' has only 1 distinct class ({y_raw.unique()}). At least 2 classes are required.",
            )
    else:
        # Regression
        if not is_numeric:
            raise DataValidationError(
                "TARGET_NOT_NUMERIC",
                f"Regression target '{target_col}' is non-numeric.",
            )
        var = float(np.var(y_raw.to_numpy(dtype=float)))
        if var == 0.0 or np.isnan(var):
            raise DataValidationError(
                "TARGET_CONSTANT",
                f"Regression target '{target_col}' has zero variance (all values are identical).",
            )

    return X_raw, y_raw, resolved_task
