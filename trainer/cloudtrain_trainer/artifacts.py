"""Artifact generation, packaging, model card rendering, and S3 uploads."""

import importlib.metadata
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
import joblib


def generate_predict_example_code() -> str:
    """Return python code for predict_example.py demonstrating offline model loading."""
    return '''#!/usr/bin/env python3
"""CloudTrain Standalone Model Inference Example.

Usage:
    python predict_example.py --data test_data.csv [--output predictions.csv]
"""

import argparse
import joblib
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="Predict with CloudTrain trained model.")
    parser.add_argument("--model", default="model.joblib", help="Path to model.joblib")
    parser.add_argument("--data", required=True, help="Path to input CSV")
    parser.add_argument("--output", default="predictions.csv", help="Path to output predictions CSV")
    args = parser.parse_args()

    # Load model package
    print(f"Loading model from {args.model}...")
    model_pkg = joblib.load(args.model)
    pipeline = model_pkg["pipeline"]
    meta = model_pkg.get("meta", {})
    task = meta.get("task", "classification")
    label_classes = meta.get("label_classes")

    # Load input data
    print(f"Loading input data from {args.data}...")
    df = pd.read_csv(args.data)

    # Predict
    print(f"Generating predictions ({task})...")
    raw_preds = pipeline.predict(df)

    if task == "classification" and label_classes:
        preds = [label_classes[int(p)] if int(p) < len(label_classes) else str(p) for p in raw_preds]
    else:
        preds = raw_preds

    df["prediction"] = preds
    df.to_csv(args.output, index=False)
    print(f"[OK] Predictions saved to {args.output}")


if __name__ == "__main__":
    main()
'''


def generate_model_card_markdown(
    config: dict[str, Any],
    metrics: dict[str, Any],
    meta: dict[str, Any],
) -> str:
    """Render model card in Markdown format."""
    model_id = config.get("model", {}).get("id", "Unknown")
    task = config.get("task", "Unknown")
    trained_at = meta.get("trained_at", datetime.now(UTC).isoformat())

    metrics_rows = []
    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            metrics_rows.append(f"| {k} | {v} |")

    metrics_table = "\n".join(metrics_rows)

    return f"""# CloudTrain Model Card — {config.get("name", "Model")}

- **Model Architecture:** `{model_id}`
- **Task:** `{task}`
- **Trained At:** `{trained_at}`
- **Input Features:** `{len(meta.get("feature_columns", []))}` columns

## Performance Metrics

| Metric | Value |
|---|---|
{metrics_table}

## Hyperparameters

```json
{json.dumps(config.get("model", {}).get("hyperparameters", {}), indent=2)}
```

## Intended Use & Safety

- **Intended Use:** Automated tabular prediction and inference.
- **Pickle / Joblib Safety Warning:** `.joblib` model artifacts must only be loaded from trusted sources. Never execute models from untrusted or unverified parties.
- **Limitations:** Performance depends on the representativeness and cleanliness of the training dataset.
"""


def save_and_upload_artifacts(
    output_dir: Path,
    pipeline: Any,
    config: dict[str, Any],
    metrics: dict[str, Any],
    feature_importance: dict[str, Any],
    preprocessing_report: dict[str, Any],
    label_classes: list[str] | None,
    feature_columns: list[str],
    task: str,
    bucket_name: str | None = None,
    user_id: str | None = None,
    job_id: str | None = None,
    s3_endpoint_url: str | None = None,
    region: str | None = None,
    log_content: str | None = None,
) -> list[dict[str, Any]]:
    """Save all artifacts locally in output_dir and upload to S3 if bucket provided."""
    output_dir.mkdir(parents=True, exist_ok=True)
    now_ts = datetime.now(UTC).isoformat()

    # Collect library versions
    lib_versions = {}
    for lib in ["scikit-learn", "xgboost", "pandas", "numpy", "joblib"]:
        try:
            lib_versions[lib] = importlib.metadata.version(lib)
        except Exception:
            lib_versions[lib] = "unknown"

    meta = {
        "label_classes": label_classes,
        "feature_columns": feature_columns,
        "task": task,
        "trained_at": now_ts,
        "library_versions": lib_versions,
    }

    # 1. model.joblib
    model_path = output_dir / "model.joblib"
    joblib.dump({"pipeline": pipeline, "meta": meta}, model_path)

    # Check size constraint (< 200 MB)
    model_size = model_path.stat().st_size
    if model_size > 200 * 1024 * 1024:
        raise ValueError(
            f"ARTIFACT_TOO_LARGE: Model artifact size ({model_size / (1024 * 1024):.1f} MB) exceeds 200 MB limit."
        )

    # 2. metrics.json
    metrics_path = output_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # 3. config.json
    config_path = output_dir / "config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    # 4. feature_importance.json
    fi_path = output_dir / "feature_importance.json"
    with open(fi_path, "w", encoding="utf-8") as f:
        json.dump(feature_importance, f, indent=2)

    # 5. preprocessing_report.json
    pr_path = output_dir / "preprocessing_report.json"
    with open(pr_path, "w", encoding="utf-8") as f:
        json.dump(preprocessing_report, f, indent=2)

    # 6. model_card.md
    mc_path = output_dir / "model_card.md"
    with open(mc_path, "w", encoding="utf-8") as f:
        f.write(generate_model_card_markdown(config, metrics, meta))

    # 7. predict_example.py
    pe_path = output_dir / "predict_example.py"
    with open(pe_path, "w", encoding="utf-8") as f:
        f.write(generate_predict_example_code())

    # 8. requirements.txt
    req_path = output_dir / "requirements.txt"
    with open(req_path, "w", encoding="utf-8") as f:
        lines = [f"{k}=={v}" for k, v in lib_versions.items() if v != "unknown"]
        f.write("\n".join(lines) + "\n")

    # 9. logs.txt
    if log_content:
        logs_path = output_dir / "logs.txt"
        with open(logs_path, "w", encoding="utf-8") as f:
            f.write(log_content)

    artifact_files = list(output_dir.iterdir())
    uploaded_records: list[dict[str, Any]] = []

    # Upload to S3 if configured
    if bucket_name and user_id and job_id:
        s3 = boto3.client(
            "s3",
            region_name=region or "ap-south-1",
            endpoint_url=s3_endpoint_url,
        )
        prefix = f"jobs/{user_id}/{job_id}/artifacts/"

        for file_path in artifact_files:
            key = f"{prefix}{file_path.name}"
            size = file_path.stat().st_size
            s3.upload_file(
                str(file_path),
                bucket_name,
                key,
                ExtraArgs={"ServerSideEncryption": "AES256"},
            )
            # Verify upload size with HeadObject
            resp = s3.head_object(Bucket=bucket_name, Key=key)
            assert resp["ContentLength"] == size, f"Size mismatch for uploaded {key}"
            uploaded_records.append(
                {
                    "name": file_path.name,
                    "key": key,
                    "size": size,
                }
            )

    return uploaded_records
