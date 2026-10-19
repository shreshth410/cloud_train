"""Unit tests for dataset profiler heuristics and S3 event handler."""

import os
from typing import Any

from common.ddb import create_dataset, get_dataset
from dataset_profiler.main import lambda_handler
from dataset_profiler.profiler import infer_column_dtype, profile_csv_content


def test_profiler_iris_csv() -> None:
    """Iris sample dataset profiles correctly."""
    iris_path = os.path.join(os.path.dirname(__file__), "..", "..", "samples", "iris.csv")
    with open(iris_path, "rb") as f:
        content = f.read()

    profile, errors = profile_csv_content(content)
    assert errors == []
    assert profile is not None
    assert profile["row_count"] == 150
    assert profile["column_count"] == 5

    col_map = {c["name"]: c for c in profile["columns"]}
    assert col_map["sepal length (cm)"]["dtype"] == "numeric"
    assert "stats" in col_map["sepal length (cm)"]
    assert col_map["target"]["dtype"] == "categorical"
    assert len(profile["preview_rows"]) == 5


def test_profiler_column_heuristics() -> None:
    """Verify dtype heuristics for each tabular type."""
    # 1. Numeric
    assert infer_column_dtype("val", ["1.2", "3.4", "5.0", "-2.1"], 25) == "numeric"

    # 2. Boolean
    assert infer_column_dtype("flag", ["true", "false", "true", "false"], 25) == "boolean"
    assert infer_column_dtype("flag_num", ["0", "1", "1", "0"], 25) == "boolean"

    # 3. Datetime
    assert infer_column_dtype("dt", ["2026-01-01", "2026-01-02", "2026-01-03"], 25) == "datetime"

    # 4. Constant
    assert infer_column_dtype("const", ["fixed", "fixed", "fixed"], 25) == "constant"

    # 5. ID-like
    id_vals = [f"uuid-{i}" for i in range(30)]
    assert infer_column_dtype("customer_id", id_vals, 30) == "id_like"

    # 6. Text
    long_sentences = [f"This is an extensive free text narrative comment number {i} for review." for i in range(30)]
    assert infer_column_dtype("comments", long_sentences, 30) == "text"


def test_profiler_validation_failures() -> None:
    """Verify validation gates: empty, duplicate header, blank header, fewer than 20 rows."""
    # Empty
    _p, errs = profile_csv_content(b"")
    assert any("empty" in e.lower() for e in errs)

    # Blank header
    _p, errs = profile_csv_content(b"a,,b\n1,2,3\n")
    assert any("blank" in e.lower() for e in errs)

    # Duplicate header
    _p, errs = profile_csv_content(b"a,b,a\n1,2,3\n")
    assert any("duplicate" in e.lower() for e in errs)

    # Fewer than 20 rows
    lines = ["a,b"] + [f"{i},{i + 1}" for i in range(10)]
    _p, errs = profile_csv_content("\n".join(lines).encode("utf-8"))
    assert any("fewer than 20" in e.lower() for e in errs)


def test_s3_event_handler(mock_aws_stack: dict[str, Any]) -> None:
    """S3 ObjectCreated event triggers profiling and updates DynamoDB."""
    s3 = mock_aws_stack["s3"]
    bucket = os.environ["DATA_BUCKET"]
    datasets_table = os.environ["DATASETS_TABLE"]

    user_id = "user-prof"
    ds_id = "ds-prof-123"
    s3_key = f"datasets/{user_id}/{ds_id}/data.csv"

    # Create dataset record
    create_dataset(
        datasets_table,
        {
            "dataset_id": ds_id,
            "user_id": user_id,
            "name": "data.csv",
            "s3_key": s3_key,
            "status": "PENDING_UPLOAD",
        },
    )

    # Put CSV into S3 (25 rows)
    lines = ["col_a,col_b"] + [f"{i},cat_{i % 3}" for i in range(25)]
    csv_bytes = "\n".join(lines).encode("utf-8")
    s3.put_object(Bucket=bucket, Key=s3_key, Body=csv_bytes)

    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": s3_key, "size": len(csv_bytes)},
                }
            }
        ]
    }

    res = lambda_handler(event)
    assert res["statusCode"] == 200
    assert res["processed"] == 1

    ds = get_dataset(datasets_table, ds_id)
    assert ds["status"] == "READY"
    assert ds["profile"]["row_count"] == 25
    assert ds["profile"]["column_count"] == 2
