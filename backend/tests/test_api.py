"""Unit and integration tests for API Gateway HTTP API handler."""

import json
import os
from typing import Any

from api.main import lambda_handler
from common.ddb import (
    create_dataset,
    create_job,
)


def make_api_event(
    method: str,
    path: str,
    user_id: str | None = "test-user-123",
    email: str = "test@example.com",
    body: dict[str, Any] | None = None,
    query_params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Helper to craft an API Gateway HTTP API payload v2.0 event."""
    hdrs = dict(headers or {})
    event: dict[str, Any] = {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": hdrs,
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
            },
        },
    }
    if user_id is not None:
        event["requestContext"]["authorizer"] = {
            "jwt": {
                "claims": {
                    "sub": user_id,
                    "email": email,
                }
            }
        }
    if body is not None:
        event["body"] = json.dumps(body)
    if query_params is not None:
        event["queryStringParameters"] = query_params

    return event


def test_auth_unauthorized(mock_aws_stack: dict[str, Any]) -> None:
    """Missing authorization token returns 401."""
    event = make_api_event("GET", "/me", user_id=None)
    resp = lambda_handler(event)
    assert resp["statusCode"] == 401
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "UNAUTHORIZED"


def test_local_auth_bypass_guard(mock_aws_stack: dict[str, Any]) -> None:
    """LOCAL_AUTH_BYPASS=1 when ENV != local must fail with 500."""
    os.environ["LOCAL_AUTH_BYPASS"] = "1"
    os.environ["ENV"] = "production"
    try:
        event = make_api_event("GET", "/me", user_id=None, headers={"x-user-sub": "local-dev"})
        resp = lambda_handler(event)
        assert resp["statusCode"] == 500
        body = json.loads(resp["body"])
        assert body["error"]["code"] == "AUTH_CONFIGURATION_ERROR"
    finally:
        os.environ["LOCAL_AUTH_BYPASS"] = "0"
        os.environ["ENV"] = "test"


def test_cors_preflight(mock_aws_stack: dict[str, Any]) -> None:
    """OPTIONS request returns 204 with CORS headers."""
    event = make_api_event("OPTIONS", "/datasets")
    resp = lambda_handler(event)
    assert resp["statusCode"] == 204
    assert "Access-Control-Allow-Origin" in resp["headers"]


def test_get_me_quotas(mock_aws_stack: dict[str, Any]) -> None:
    """GET /me returns user quotas and current usage."""
    event = make_api_event("GET", "/me", user_id="user-a", email="user-a@example.com")
    resp = lambda_handler(event)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["user_id"] == "user-a"
    assert body["email"] == "user-a@example.com"
    assert body["quotas"]["datasets_used"] == 0
    assert body["quotas"]["active_jobs"] == 0
    assert body["quotas"]["datasets_max"] == 10
    assert body["quotas"]["active_jobs_max"] == 3


def test_get_models_registry(mock_aws_stack: dict[str, Any]) -> None:
    """GET /models returns the models registry JSON."""
    event = make_api_event("GET", "/models")
    resp = lambda_handler(event)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert "models" in body
    model_ids = [m["id"] for m in body["models"]]
    assert "random_forest" in model_ids


def test_dataset_lifecycle(mock_aws_stack: dict[str, Any]) -> None:
    """Full lifecycle: create dataset, list, detail, and delete."""
    user_id = "user-ds-1"

    # 1. Invalid filename (not .csv)
    bad_req = make_api_event("POST", "/datasets", user_id=user_id, body={"name": "data.txt"})
    resp = lambda_handler(bad_req)
    assert resp["statusCode"] == 400
    assert json.loads(resp["body"])["error"]["code"] == "INVALID_FILENAME"

    # 2. Valid dataset creation
    good_req = make_api_event("POST", "/datasets", user_id=user_id, body={"name": "my_dataset.csv"})
    resp = lambda_handler(good_req)
    assert resp["statusCode"] == 201
    created = json.loads(resp["body"])
    ds_id = created["dataset_id"]
    assert "upload" in created
    assert "url" in created["upload"]
    assert "fields" in created["upload"]

    # 3. GET /datasets (list)
    list_req = make_api_event("GET", "/datasets", user_id=user_id)
    resp = lambda_handler(list_req)
    assert resp["statusCode"] == 200
    items = json.loads(resp["body"])["items"]
    assert len(items) == 1
    assert items[0]["dataset_id"] == ds_id

    # 4. GET /datasets/{id}
    detail_req = make_api_event("GET", f"/datasets/{ds_id}", user_id=user_id)
    resp = lambda_handler(detail_req)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["dataset_id"] == ds_id

    # 5. User isolation: other user cannot see it
    other_req = make_api_event("GET", f"/datasets/{ds_id}", user_id="user-intruder")
    assert lambda_handler(other_req)["statusCode"] == 404

    # 6. DELETE /datasets/{id}
    del_req = make_api_event("DELETE", f"/datasets/{ds_id}", user_id=user_id)
    assert lambda_handler(del_req)["statusCode"] == 204

    # Confirm deleted
    assert lambda_handler(detail_req)["statusCode"] == 404


def test_delete_dataset_in_use_rejected(mock_aws_stack: dict[str, Any]) -> None:
    """Deleting a dataset referenced by an active job returns 409 DATASET_IN_USE."""
    user_id = "user-busy"
    ds_id = "ds-active"
    jobs_table = os.environ["JOBS_TABLE"]
    datasets_table = os.environ["DATASETS_TABLE"]

    create_dataset(
        datasets_table,
        {
            "dataset_id": ds_id,
            "user_id": user_id,
            "name": "active.csv",
            "s3_key": f"datasets/{user_id}/{ds_id}/data.csv",
            "status": "READY",
        },
    )

    create_job(
        jobs_table,
        {
            "job_id": "job-running-1",
            "user_id": user_id,
            "dataset_id": ds_id,
            "status": "RUNNING",
            "stage": "TRAINING",
            "name": "Active Job",
        },
    )

    del_req = make_api_event("DELETE", f"/datasets/{ds_id}", user_id=user_id)
    resp = lambda_handler(del_req)
    assert resp["statusCode"] == 409
    body = json.loads(resp["body"])
    assert body["error"]["code"] == "DATASET_IN_USE"


def test_jobs_submission_and_lifecycle(mock_aws_stack: dict[str, Any]) -> None:
    """Test job submission, query, cancellation, logs, artifacts, results, and deletion."""
    user_id = "user-job-tester"
    ds_id = "ds-ready-1"
    datasets_table = os.environ["DATASETS_TABLE"]
    data_bucket = os.environ["DATA_BUCKET"]

    # Seed READY dataset
    create_dataset(
        datasets_table,
        {
            "dataset_id": ds_id,
            "user_id": user_id,
            "name": "iris.csv",
            "s3_key": f"datasets/{user_id}/{ds_id}/data.csv",
            "status": "READY",
            "profile": {
                "columns": [
                    {"name": "sepal_length", "dtype": "numeric", "missing_pct": 0},
                    {"name": "sepal_width", "dtype": "numeric", "missing_pct": 0},
                    {"name": "species", "dtype": "categorical", "missing_pct": 0, "unique_count": 3},
                ],
                "row_count": 150,
                "column_count": 3,
            },
        },
    )

    # 1. Submit valid job
    job_cfg = {
        "name": "Iris Classifier",
        "dataset_id": ds_id,
        "target_column": "species",
        "model": {"id": "random_forest", "hyperparameters": {"n_estimators": 50}},
    }
    submit_req = make_api_event("POST", "/jobs", user_id=user_id, body=job_cfg)
    resp = lambda_handler(submit_req)
    assert resp["statusCode"] == 202
    res_body = json.loads(resp["body"])
    job_id = res_body["job_id"]
    assert res_body["status"] == "QUEUED"

    # Verify S3 config.json written
    s3 = mock_aws_stack["s3"]
    cfg_obj = s3.get_object(Bucket=data_bucket, Key=f"jobs/{user_id}/{job_id}/config.json")
    saved_cfg = json.loads(cfg_obj["Body"].read().decode("utf-8"))
    assert saved_cfg["task"] == "classification"

    # 2. GET /jobs (list)
    list_req = make_api_event("GET", "/jobs", user_id=user_id)
    resp = lambda_handler(list_req)
    assert resp["statusCode"] == 200
    jobs_list = json.loads(resp["body"])["items"]
    assert len(jobs_list) == 1
    assert jobs_list[0]["job_id"] == job_id

    # 3. GET /jobs/{id}
    detail_req = make_api_event("GET", f"/jobs/{job_id}", user_id=user_id)
    resp = lambda_handler(detail_req)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["job_id"] == job_id

    # 4. User isolation: other user cannot see job
    other_req = make_api_event("GET", f"/jobs/{job_id}", user_id="intruder")
    assert lambda_handler(other_req)["statusCode"] == 404

    # 5. POST /jobs/{id}/cancel (QUEUED -> CANCELLED)
    cancel_req = make_api_event("POST", f"/jobs/{job_id}/cancel", user_id=user_id)
    resp = lambda_handler(cancel_req)
    assert resp["statusCode"] == 202
    assert json.loads(resp["body"])["status"] == "CANCELLED"

    # 6. DELETE /jobs/{id} (terminal -> 204)
    del_req = make_api_event("DELETE", f"/jobs/{job_id}", user_id=user_id)
    assert lambda_handler(del_req)["statusCode"] == 204

    # Confirm deleted
    assert lambda_handler(detail_req)["statusCode"] == 404


def test_job_artifacts_and_results_succeeded(mock_aws_stack: dict[str, Any]) -> None:
    """GET /jobs/{id}/artifacts and /results return 200 when SUCCEEDED."""
    user_id = "user-succ"
    job_id = "job-succ-123"
    jobs_table = os.environ["JOBS_TABLE"]
    data_bucket = os.environ["DATA_BUCKET"]
    s3 = mock_aws_stack["s3"]

    create_job(
        jobs_table,
        {
            "job_id": job_id,
            "user_id": user_id,
            "status": "SUCCEEDED",
            "stage": "DONE",
            "progress": 100,
            "name": "Succeeded Job",
        },
    )

    # Seed artifacts in S3
    s3.put_object(
        Bucket=data_bucket,
        Key=f"jobs/{user_id}/{job_id}/artifacts/metrics.json",
        Body=json.dumps({"accuracy": 0.96}),
    )
    s3.put_object(
        Bucket=data_bucket,
        Key=f"jobs/{user_id}/{job_id}/artifacts/feature_importance.json",
        Body=json.dumps({"importances": {"sepal_length": 0.4}}),
    )
    s3.put_object(
        Bucket=data_bucket,
        Key=f"jobs/{user_id}/{job_id}/artifacts/model.joblib",
        Body=b"fake-model-binary",
    )

    # GET /artifacts
    art_req = make_api_event("GET", f"/jobs/{job_id}/artifacts", user_id=user_id)
    resp = lambda_handler(art_req)
    assert resp["statusCode"] == 200
    files = json.loads(resp["body"])["files"]
    names = [f["name"] for f in files]
    assert "metrics.json" in names
    assert "model.joblib" in names

    # GET /results
    res_req = make_api_event("GET", f"/jobs/{job_id}/results", user_id=user_id)
    resp = lambda_handler(res_req)
    assert resp["statusCode"] == 200
    results = json.loads(resp["body"])
    assert results["metrics"]["accuracy"] == 0.96
    assert results["feature_importance"]["importances"]["sepal_length"] == 0.4
