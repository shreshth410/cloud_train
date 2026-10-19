"""Training job configuration loader and validator."""

import json
from pathlib import Path
from typing import Any

import boto3
import jsonschema


def find_shared_file(filename: str) -> Path:
    """Find files in shared directory across local repo and container environments."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "shared" / filename,
        Path("/app/shared") / filename,
        Path("shared") / filename,
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(f"Could not locate shared file: {filename}")


def load_job_config(
    user_id: str,
    job_id: str,
    bucket_name: str | None = None,
    s3_endpoint_url: str | None = None,
    region: str | None = None,
    local_config_path: str | None = None,
) -> dict[str, Any]:
    """Load configuration from local file or S3."""
    if local_config_path:
        with open(local_config_path, encoding="utf-8") as f:
            config = json.load(f)
    else:
        assert bucket_name, "DATA_BUCKET must be specified if not using local_config_path"
        s3 = boto3.client(
            "s3",
            region_name=region or "ap-south-1",
            endpoint_url=s3_endpoint_url,
        )
        key = f"jobs/{user_id}/{job_id}/config.json"
        resp = s3.get_object(Bucket=bucket_name, Key=key)
        config = json.loads(resp["Body"].read().decode("utf-8"))

    # Validate against JSON schema
    schema_path = find_shared_file("job_config.schema.json")
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)

    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(config)

    # Validate model against model registry
    registry_path = find_shared_file("model_registry.json")
    with open(registry_path, encoding="utf-8") as f:
        registry = json.load(f)

    model_id = config["model"]["id"]
    model_spec = None
    for m in registry.get("models", []):
        if m["id"] == model_id:
            model_spec = m
            break
    if not model_spec:
        raise ValueError(f"Unknown model id in config: {model_id}")

    # Fill defaults
    config.setdefault("task", "auto")
    config.setdefault("feature_columns", None)
    config.setdefault("max_runtime_minutes", 30)

    prep = config.setdefault("preprocessing", {})
    prep.setdefault("numeric_impute", "median")
    prep.setdefault("categorical_impute", "most_frequent")
    prep.setdefault("scale_numeric", True)
    prep.setdefault("max_categories", 50)
    prep.setdefault("drop_id_like", True)

    split = config.setdefault("split", {})
    split.setdefault("test_size", 0.2)
    split.setdefault("stratify", True)
    split.setdefault("random_state", 42)

    cv = config.setdefault("cross_validation", {})
    cv.setdefault("folds", 0)

    # Force scale_numeric if model needs scaling
    if model_spec.get("needs_scaling", False):
        config["preprocessing"]["scale_numeric"] = True

    # Fill default hyperparameters
    user_hp = config["model"].setdefault("hyperparameters", {})
    for hp in model_spec.get("hyperparameters", []):
        name = hp["name"]
        if name not in user_hp:
            user_hp[name] = hp.get("default")

    return config
