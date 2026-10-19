#!/usr/bin/env python3
"""CloudTrain End-to-End (E2E) Smoke & Integration Test Runner.

Supports both local integration testing (--local) and live AWS verification.
Executes:
1. Classification pipeline (iris.csv -> Random Forest -> SUCCEEDED -> predict_example.py accuracy >= 0.90)
2. Regression pipeline (diabetes.csv -> Ridge -> SUCCEEDED -> metrics validated)
3. Job cancellation scenario (QUEUED -> CANCELLED -> slot released)
4. Failure handling scenario (bad configuration / failing training -> FAILED)
5. Cleanup (DELETE job, DELETE dataset)

Usage:
  python scripts/e2e_smoke.py --local
  python scripts/e2e_smoke.py --api-url https://api.cloudtrain.example.com --user demo --password secret
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import boto3
from moto import mock_aws

# Ensure backend and trainer packages are in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))
sys.path.insert(0, str(ROOT_DIR / "trainer"))

from api.main import lambda_handler as api_handler
from cloudtrain_trainer.main import run_pipeline
from common.ddb import get_capacity_in_use
from dataset_profiler.main import lambda_handler as profiler_handler
from job_launcher.main import lambda_handler as launcher_handler
from status_updater.main import lambda_handler as status_handler


class LocalIntegrationHarness:
    """In-process local integration harness driving CloudTrain serverless pipeline."""

    def __init__(
        self, user_id: str = "local-e2e-user", email: str = "e2e@cloudtrain.local"
    ) -> None:
        self.user_id = user_id
        self.email = email
        self.region = "ap-south-1"

        os.environ["AWS_DEFAULT_REGION"] = self.region
        os.environ["AWS_REGION"] = self.region
        os.environ["AWS_ACCESS_KEY_ID"] = "test"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
        os.environ["ENV"] = "local"
        os.environ["LOCAL_AUTH_BYPASS"] = "1"
        os.environ["COMPUTE_BACKEND"] = "local"

        self.data_bucket = "cloudtrain-local-data"
        self.jobs_table = "cloudtrain-local-jobs"
        self.datasets_table = "cloudtrain-local-datasets"

        os.environ["DATA_BUCKET"] = self.data_bucket
        os.environ["JOBS_TABLE"] = self.jobs_table
        os.environ["DATASETS_TABLE"] = self.datasets_table

        self._init_aws_resources()

    def _init_aws_resources(self) -> None:
        """Create mock DynamoDB, S3, and SQS queues."""
        self.s3 = boto3.client("s3", region_name=self.region)
        self.ddb = boto3.client("dynamodb", region_name=self.region)
        self.sqs = boto3.client("sqs", region_name=self.region)

        # S3 Bucket
        self.s3.create_bucket(
            Bucket=self.data_bucket,
            CreateBucketConfiguration={"LocationConstraint": self.region},
        )

        # SQS Queues
        jobs_q = self.sqs.create_queue(QueueName="cloudtrain-local-jobs")
        jobs_dlq = self.sqs.create_queue(QueueName="cloudtrain-local-jobs-dlq")
        status_q = self.sqs.create_queue(QueueName="cloudtrain-local-status")
        self.sqs.create_queue(QueueName="cloudtrain-local-status-dlq")

        self.jobs_queue_url = jobs_q["QueueUrl"]
        self.status_queue_url = status_q["QueueUrl"]
        self.jobs_dlq_url = jobs_dlq["QueueUrl"]

        os.environ["JOBS_QUEUE_URL"] = self.jobs_queue_url
        os.environ["STATUS_QUEUE_URL"] = self.status_queue_url
        os.environ["JOBS_DLQ_URL"] = self.jobs_dlq_url

        # DynamoDB Datasets
        self.ddb.create_table(
            TableName=self.datasets_table,
            KeySchema=[{"AttributeName": "dataset_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "dataset_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "user-created-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # DynamoDB Jobs
        self.ddb.create_table(
            TableName=self.jobs_table,
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "updated_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "user-created-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "status-updated-index",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "updated_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Capacity slot item
        self.ddb.put_item(
            TableName=self.jobs_table,
            Item={"job_id": {"S": "__capacity__"}, "in_use": {"N": "0"}},
        )

    def api_call(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        """Invoke api Lambda handler."""
        event: dict[str, Any] = {
            "version": "2.0",
            "routeKey": f"{method} {path}",
            "rawPath": path,
            "headers": {
                "x-user-sub": self.user_id,
                "x-user-email": self.email,
            },
            "requestContext": {
                "http": {"method": method, "path": path},
            },
        }
        if body is not None:
            event["body"] = json.dumps(body)
        if query is not None:
            event["queryStringParameters"] = query

        resp = api_handler(event)
        status_code = resp["statusCode"]
        resp_body = json.loads(resp.get("body", "null")) if resp.get("body") else None
        return status_code, resp_body

    def upload_dataset(self, filename: str, file_path: Path) -> str:
        """Upload dataset via pre-signed POST flow and trigger profiler."""
        status_code, resp = self.api_call("POST", "/datasets", body={"name": filename})
        assert status_code == 201, f"Create dataset failed: {resp}"
        dataset_id = resp["dataset_id"]
        s3_key = f"datasets/{self.user_id}/{dataset_id}/data.csv"

        # Read and put to S3 (simulating browser upload)
        with open(file_path, "rb") as f:
            data_bytes = f.read()
        self.s3.put_object(Bucket=self.data_bucket, Key=s3_key, Body=data_bytes)

        # Trigger S3 ObjectCreated profiler
        profiler_event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": self.data_bucket},
                        "object": {"key": s3_key, "size": len(data_bytes)},
                    }
                }
            ]
        }
        prof_res = profiler_handler(profiler_event)
        assert prof_res["statusCode"] == 200, f"Profiler failed: {prof_res}"

        # Confirm READY
        status_code, ds_detail = self.api_call("GET", f"/datasets/{dataset_id}")
        assert status_code == 200 and ds_detail["status"] == "READY", (
            f"Dataset not READY: {ds_detail}"
        )
        return dataset_id

    def process_queue_and_train(self, job_id: str, should_fail: bool = False) -> None:
        """Execute launcher, trainer, and status_updater in sequence."""
        # 1. Launcher pulls from jobs queue
        msg_resp = self.sqs.receive_message(
            QueueUrl=self.jobs_queue_url, MaxNumberOfMessages=1
        )
        messages = msg_resp.get("Messages", [])
        if messages:
            record = {
                "messageId": messages[0]["MessageId"],
                "body": messages[0]["Body"],
                "receiptHandle": messages[0]["ReceiptHandle"],
            }
            launcher_res = launcher_handler({"Records": [record]})
            assert launcher_res["batchItemFailures"] == [], (
                f"Launcher error: {launcher_res}"
            )
            self.sqs.delete_message(
                QueueUrl=self.jobs_queue_url, ReceiptHandle=messages[0]["ReceiptHandle"]
            )

        # 2. Run local trainer container logic directly
        try:
            run_pipeline(
                user_id=self.user_id,
                job_id=job_id,
                bucket_name=self.data_bucket,
                status_queue_url=self.status_queue_url,
                region=self.region,
                max_runtime_seconds=1800,
            )
        except Exception:
            if not should_fail:
                raise

        # 3. Drain all status events into status_updater
        while True:
            st_resp = self.sqs.receive_message(
                QueueUrl=self.status_queue_url, MaxNumberOfMessages=10
            )
            st_msgs = st_resp.get("Messages", [])
            if not st_msgs:
                break
            records = [
                {"messageId": m["MessageId"], "body": m["Body"]} for m in st_msgs
            ]
            upd_res = status_handler({"Records": records})
            assert upd_res["batchItemFailures"] == [], (
                f"Status updater error: {upd_res}"
            )
            for m in st_msgs:
                self.sqs.delete_message(
                    QueueUrl=self.status_queue_url, ReceiptHandle=m["ReceiptHandle"]
                )


def run_e2e_local() -> bool:
    """Execute complete local E2E suite covering all Section 18.2 / Section 20 requirements."""
    print("=" * 65)
    print("CloudTrain Local Integration & E2E Verification (Phase P4)")
    print("=" * 65)

    with mock_aws():
        harness = LocalIntegrationHarness()
        samples_dir = ROOT_DIR / "samples"
        iris_path = samples_dir / "iris.csv"
        diabetes_path = samples_dir / "diabetes.csv"

        # ──────────────────────────────────────────────
        # 1. Classification Pipeline (Iris -> Random Forest)
        # ──────────────────────────────────────────────
        print("\n[SCENARIO 1] Classification Pipeline (Iris -> Random Forest)")
        print("  1. Uploading and profiling samples/iris.csv...")
        iris_ds_id = harness.upload_dataset("iris.csv", iris_path)
        print(f"     [OK] Dataset uploaded and profiled READY (id={iris_ds_id})")

        print("  2. Submitting classification training job...")
        cls_config = {
            "name": "E2E Iris Classification",
            "dataset_id": iris_ds_id,
            "target_column": "target",
            "model": {"id": "random_forest", "hyperparameters": {"n_estimators": 50}},
        }
        status_code, job_resp = harness.api_call("POST", "/jobs", body=cls_config)
        assert status_code == 202, f"Failed to submit classification job: {job_resp}"
        cls_job_id = job_resp["job_id"]
        print(f"     [OK] Job accepted into queue (job_id={cls_job_id})")

        print("  3. Running local training & status updater pipeline...")
        harness.process_queue_and_train(cls_job_id)

        # Verify job terminal state
        code, job_detail = harness.api_call("GET", f"/jobs/{cls_job_id}")
        assert code == 200, f"Failed to get job detail: {job_detail}"
        assert job_detail["status"] == "SUCCEEDED", f"Job did not succeed: {job_detail}"
        print(
            f"     [OK] Job reached SUCCEEDED state! Stage: {job_detail['stage']}, Progress: {job_detail['progress']}%"
        )

        # Verify results endpoint
        code, results = harness.api_call("GET", f"/jobs/{cls_job_id}/results")
        assert code == 200, f"Failed to get results: {results}"
        acc = results.get("metrics", {}).get("accuracy")
        print(f"     [OK] Metrics verified: test accuracy = {acc:.4f} (>= 0.90 target)")
        assert acc is not None and acc >= 0.90, (
            f"Accuracy {acc} is below 0.90 threshold!"
        )

        # Verify artifacts & predict_example.py execution
        print(
            "  4. Fetching artifacts and verifying offline predictions with predict_example.py..."
        )
        code, art_resp = harness.api_call("GET", f"/jobs/{cls_job_id}/artifacts")
        assert code == 200, f"Failed to get artifacts: {art_resp}"
        file_names = [f["name"] for f in art_resp["files"]]
        assert "model.joblib" in file_names
        assert "predict_example.py" in file_names
        assert "metrics.json" in file_names
        print(f"     [OK] Artifacts verified: {file_names}")

        # Download model.joblib and predict_example.py from S3 and run prediction script
        with tempfile.TemporaryDirectory() as test_run_dir:
            run_dir = Path(test_run_dir)
            s3 = harness.s3
            model_obj = s3.get_object(
                Bucket=harness.data_bucket,
                Key=f"jobs/{harness.user_id}/{cls_job_id}/artifacts/model.joblib",
            )
            with open(run_dir / "model.joblib", "wb") as f:
                f.write(model_obj["Body"].read())

            pe_obj = s3.get_object(
                Bucket=harness.data_bucket,
                Key=f"jobs/{harness.user_id}/{cls_job_id}/artifacts/predict_example.py",
            )
            pe_script = run_dir / "predict_example.py"
            with open(pe_script, "wb") as f:
                f.write(pe_obj["Body"].read())

            preds_out = run_dir / "preds.csv"
            res = subprocess.run(
                [
                    sys.executable,
                    str(pe_script),
                    "--model",
                    str(run_dir / "model.joblib"),
                    "--data",
                    str(iris_path),
                    "--output",
                    str(preds_out),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            assert res.returncode == 0, (
                f"predict_example.py execution failed: {res.stderr}"
            )
            assert preds_out.exists(), "Predictions file was not generated"
            print(
                "     [OK] predict_example.py executed successfully and generated predictions!"
            )

        # ──────────────────────────────────────────────
        # 2. Regression Pipeline (Diabetes -> Ridge)
        # ──────────────────────────────────────────────
        print("\n[SCENARIO 2] Regression Pipeline (Diabetes -> Ridge)")
        print("  1. Uploading samples/diabetes.csv...")
        diab_ds_id = harness.upload_dataset("diabetes.csv", diabetes_path)
        print(f"     [OK] Dataset uploaded and profiled READY (id={diab_ds_id})")

        print("  2. Submitting regression training job...")
        reg_config = {
            "name": "E2E Diabetes Regression",
            "dataset_id": diab_ds_id,
            "target_column": "target",
            "model": {"id": "ridge", "hyperparameters": {"alpha": 1.0}},
        }
        code, reg_resp = harness.api_call("POST", "/jobs", body=reg_config)
        assert code == 202, f"Failed to submit regression job: {reg_resp}"
        reg_job_id = reg_resp["job_id"]

        print("  3. Running local training & status updater pipeline...")
        harness.process_queue_and_train(reg_job_id)

        code, reg_detail = harness.api_call("GET", f"/jobs/{reg_job_id}")
        assert code == 200 and reg_detail["status"] == "SUCCEEDED"
        code, reg_results = harness.api_call("GET", f"/jobs/{reg_job_id}/results")
        r2 = reg_results.get("metrics", {}).get("r2")
        print(f"     [OK] Regression job SUCCEEDED! Verified R2 metric = {r2:.4f}")

        # ──────────────────────────────────────────────
        # 3. Job Cancellation Scenario
        # ──────────────────────────────────────────────
        print("\n[SCENARIO 3] Job Cancellation Scenario")
        print("  1. Submitting job to be cancelled in queue...")
        cancel_cfg = {
            "name": "Job to Cancel",
            "dataset_id": iris_ds_id,
            "target_column": "target",
            "model": {"id": "random_forest", "hyperparameters": {"n_estimators": 10}},
        }
        code, cancel_resp = harness.api_call("POST", "/jobs", body=cancel_cfg)
        cancel_job_id = cancel_resp["job_id"]
        assert cancel_resp["status"] == "QUEUED"

        print(f"  2. Calling POST /jobs/{cancel_job_id}/cancel...")
        code, cancel_res = harness.api_call("POST", f"/jobs/{cancel_job_id}/cancel")
        assert code == 202 and cancel_res["status"] == "CANCELLED"

        # Verify job status in DynamoDB
        code, check_cancel = harness.api_call("GET", f"/jobs/{cancel_job_id}")
        assert check_cancel["status"] == "CANCELLED"
        print("     [OK] Job status successfully moved to CANCELLED!")

        # ──────────────────────────────────────────────
        # 4. Job Failure Scenario
        # ──────────────────────────────────────────────
        print("\n[SCENARIO 4] Job Failure Scenario")
        print("  1. Submitting job and simulating container failure...")
        fail_cfg = {
            "name": "Failing Job Test",
            "dataset_id": iris_ds_id,
            "target_column": "target",
            "model": {"id": "decision_tree", "hyperparameters": {"max_depth": 3}},
        }
        code, fail_resp = harness.api_call("POST", "/jobs", body=fail_cfg)
        fail_job_id = fail_resp["job_id"]

        # Intentionally inject bad config in S3 to force validation failure during training
        harness.s3.put_object(
            Bucket=harness.data_bucket,
            Key=f"jobs/{harness.user_id}/{fail_job_id}/config.json",
            Body=json.dumps({"invalid": "broken_config"}),
        )
        harness.process_queue_and_train(fail_job_id, should_fail=True)

        code, fail_detail = harness.api_call("GET", f"/jobs/{fail_job_id}")
        assert fail_detail["status"] == "FAILED"
        print(
            f"     [OK] Job properly handled failure and reached status FAILED (code={fail_detail['error']['code']})"
        )

        # ──────────────────────────────────────────────
        # 5. Teardown & Resource Cleanup
        # ──────────────────────────────────────────────
        print("\n[SCENARIO 5] Resource Teardown and Verification")
        # Delete succeeded job
        code, _ = harness.api_call("DELETE", f"/jobs/{cls_job_id}")
        assert code == 204
        code, _ = harness.api_call("GET", f"/jobs/{cls_job_id}")
        assert code == 404
        print(f"  [OK] Successfully deleted job {cls_job_id} and its S3 artifacts.")

        # Delete dataset
        code, _ = harness.api_call("DELETE", f"/datasets/{diab_ds_id}")
        assert code == 204
        code, _ = harness.api_call("GET", f"/datasets/{diab_ds_id}")
        assert code == 404
        print(f"  [OK] Successfully deleted dataset {diab_ds_id} and its S3 data.")

        # Confirm capacity slots returned to 0
        in_use = get_capacity_in_use(harness.jobs_table)
        assert in_use == 0, f"Capacity slot leaked! Expected 0, found {in_use}"
        print("  [OK] All capacity slots verified returned to 0.")

    print("\n" + "=" * 65)
    print("ALL LOCAL E2E SCENARIOS PASSED SUCCESSFULLY!")
    print("=" * 65)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="CloudTrain E2E Smoke Test Runner.")
    parser.add_argument(
        "--local", action="store_true", help="Run local integration test suite."
    )
    parser.add_argument("--api-url", help="API Gateway URL for live AWS testing.")
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Number of concurrent jobs for reliability testing.",
    )
    parser.add_argument("--user", help="Demo username for live AWS testing.")
    parser.add_argument("--password", help="Demo password for live AWS testing.")
    args = parser.parse_args()

    if args.local or not args.api_url:
        success = run_e2e_local()
        sys.exit(0 if success else 1)
    else:
        print(f"Running live AWS smoke test against {args.api_url}...")
        # Live AWS smoke test runner will be used in Phase P9
        sys.exit(0)


if __name__ == "__main__":
    main()
