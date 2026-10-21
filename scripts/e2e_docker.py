"""Exercise the running Docker stack over HTTP (no mocked handlers)."""

import argparse
import time
import uuid
from pathlib import Path

import requests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default="http://localhost:5173/api")
    args = parser.parse_args()
    session = requests.Session()
    session.headers["x-user-sub"] = f"smoke-{uuid.uuid4()}"
    base = args.api_url.rstrip("/")

    def call(method, path, **kwargs):
        response = session.request(method, base + path, timeout=30, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else None

    def wait(path, statuses):
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            result = call("GET", path)
            if result["status"] in statuses:
                return result
            time.sleep(2)
        raise AssertionError(f"Timed out waiting for {path}: {result}")

    call("GET", "/models")
    for filename, model, task in [
        ("iris.csv", "random_forest", "classification"),
        ("diabetes.csv", "ridge", "regression"),
    ]:
        file = Path(__file__).resolve().parents[1] / "samples" / filename
        upload = call(
            "POST",
            "/datasets",
            json={"filename": filename, "size_bytes": file.stat().st_size},
        )
        dataset_id = upload["dataset_id"]
        preflight = requests.options(
            upload["upload"]["url"],
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
            timeout=15,
        )
        preflight.raise_for_status()
        assert preflight.headers.get("Access-Control-Allow-Origin") in (
            "*",
            "http://localhost:5173",
        )
        with file.open("rb") as stream:
            response = requests.post(
                upload["upload"]["url"],
                data=upload["upload"]["fields"],
                files={"file": (filename, stream, "text/csv")},
                timeout=30,
            )
        response.raise_for_status()
        dataset = wait("/datasets/" + dataset_id, {"READY", "INVALID"})
        assert dataset["status"] == "READY", dataset
        target = dataset["profile"]["columns"][-1]["name"]
        cancelled = call(
            "POST",
            "/jobs",
            json={
                "name": "Docker cancellation",
                "dataset_id": dataset_id,
                "target_column": target,
                "task": task,
                "model": {"id": model, "hyperparameters": {}},
            },
        )
        call("POST", "/jobs/" + cancelled["job_id"] + "/cancel")
        assert call("GET", "/jobs/" + cancelled["job_id"])["status"] == "CANCELLED"
        call("DELETE", "/jobs/" + cancelled["job_id"])
        job = call(
            "POST",
            "/jobs",
            json={
                "name": "Docker smoke " + task,
                "dataset_id": dataset_id,
                "target_column": target,
                "task": task,
                "model": {"id": model, "hyperparameters": {}},
                "compute": {"size": "small"},
            },
        )
        job_id = job["job_id"]
        result = wait("/jobs/" + job_id, {"SUCCEEDED", "FAILED", "TIMED_OUT"})
        assert result["status"] == "SUCCEEDED", result
        metrics = call("GET", "/jobs/" + job_id + "/results")["metrics"]
        assert (
            metrics["accuracy"] >= 0.9
            if task == "classification"
            else metrics["r2"] > 0
        )
        artifacts = call("GET", "/jobs/" + job_id + "/artifacts")["files"]
        assert any(item["name"] == "model.joblib" for item in artifacts)
        for item in artifacts:
            download = requests.get(item["url"], timeout=30)
            download.raise_for_status()
            assert len(download.content) == item["size"]
        assert call("GET", "/jobs/" + job_id + "/logs")["lines"]
        print(
            f"PASS {task}: upload, CORS, profile, Docker training, metrics, logs, {len(artifacts)} downloads",
            flush=True,
        )
        call("DELETE", "/jobs/" + job_id)
        call("DELETE", "/datasets/" + dataset_id)
    invalid_csv = b"x,target\n1,0\n"
    upload = call(
        "POST",
        "/datasets",
        json={"filename": "invalid.csv", "size_bytes": len(invalid_csv)},
    )
    response = requests.post(
        upload["upload"]["url"],
        data=upload["upload"]["fields"],
        files={"file": ("invalid.csv", invalid_csv, "text/csv")},
        timeout=30,
    )
    response.raise_for_status()
    invalid = wait("/datasets/" + upload["dataset_id"], {"INVALID", "READY"})
    assert invalid["status"] == "INVALID" and invalid["errors"], invalid
    call("DELETE", "/datasets/" + upload["dataset_id"])
    print("PASS invalid CSV: clear profiling failure", flush=True)
    print("Docker HTTP smoke test passed.", flush=True)


if __name__ == "__main__":
    main()
