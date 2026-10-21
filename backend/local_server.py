#!/usr/bin/env python3
"""Local HTTP API Server & Event Dispatcher for CloudTrain.

Listens on http://localhost:8000. Translates HTTP requests to API Gateway v2
events and routes them to backend/api/main.py:lambda_handler. Also starts
an embedded Moto cloud emulator on port 4566 (if not running) and polls local
queues to invoke job_launcher, dataset_profiler, and status_updater.
"""

import contextlib
import json
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

# Setup paths
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))
sys.path.insert(0, str(ROOT_DIR / "trainer"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

# Default environment configuration for LocalStack / Moto
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://127.0.0.1:4566")
os.environ.setdefault("S3_ENDPOINT_URL", "http://127.0.0.1:4566")
os.environ.setdefault("DDB_ENDPOINT_URL", "http://127.0.0.1:4566")
os.environ.setdefault("SQS_ENDPOINT_URL", "http://127.0.0.1:4566")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("LOCAL_AUTH_BYPASS", "1")
os.environ.setdefault("COMPUTE_BACKEND", "local")
os.environ.setdefault("DATA_BUCKET", "cloudtrain-local-data")
os.environ.setdefault("JOBS_TABLE", "cloudtrain-local-jobs")
os.environ.setdefault("DATASETS_TABLE", "cloudtrain-local-datasets")
os.environ.setdefault("JOBS_QUEUE_URL", "http://127.0.0.1:4566/000000000000/cloudtrain-local-jobs")
os.environ.setdefault("STATUS_QUEUE_URL", "http://127.0.0.1:4566/000000000000/cloudtrain-local-status")
os.environ.setdefault("TRAINER_IMAGE_URI", "cloudtrain-trainer:latest")
os.environ.setdefault("MAX_CONCURRENT_INSTANCES", "2")
os.environ.setdefault("MAX_DATASETS_PER_USER", "50")
os.environ.setdefault("CORS_ALLOW_ORIGIN", "*")

import boto3  # noqa: E402
from bootstrap_local import bootstrap_local_resources  # noqa: E402
from moto.server import ThreadedMotoServer  # noqa: E402

from api.main import lambda_handler as api_handler  # noqa: E402
from dataset_profiler.main import lambda_handler as profiler_handler  # noqa: E402
from job_launcher.main import lambda_handler as launcher_handler  # noqa: E402
from status_updater.main import lambda_handler as status_handler  # noqa: E402


class CloudTrainHttpHandler(BaseHTTPRequestHandler):
    """Translates incoming HTTP requests to API Gateway v2 payloads."""

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Authorization, Content-Type, x-user-sub, x-user-email, sub, *",
        )

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        self._handle_request("GET")

    def do_POST(self) -> None:
        self._handle_request("POST")

    def do_PUT(self) -> None:
        self._handle_request("PUT")

    def do_DELETE(self) -> None:
        self._handle_request("DELETE")

    def _handle_request(self, method: str) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        raw_query = parsed_url.query
        query_params = {k: v[0] for k, v in urllib.parse.parse_qs(raw_query).items()}

        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b""
        body_str = body_bytes.decode("utf-8") if body_bytes else None

        user_id = self.headers.get("x-user-sub") or self.headers.get("sub") or "local-user"
        email = self.headers.get("x-user-email") or "local-engineer@cloudtrain.dev"

        headers_dict = dict(self.headers.items())
        headers_dict["x-user-sub"] = user_id
        headers_dict["sub"] = user_id
        headers_dict["x-user-email"] = email

        # Construct API Gateway v2 payload
        event = {
            "rawPath": path,
            "rawQueryString": raw_query,
            "requestContext": {
                "http": {
                    "method": method,
                    "path": path,
                    "protocol": "HTTP/1.1",
                    "sourceIp": self.client_address[0],
                },
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": user_id,
                            "email": email,
                        }
                    }
                },
            },
            "headers": headers_dict,
            "queryStringParameters": query_params,
            "body": body_str,
            "isBase64Encoded": False,
        }

        try:
            resp = api_handler(event, None)
            status_code = resp.get("statusCode", 500)
            resp_headers = resp.get("headers", {})
            resp_body = resp.get("body", "")

            self.send_response(status_code)
            has_cors = any(k.lower() == "access-control-allow-origin" for k in resp_headers)
            for k, v in resp_headers.items():
                self.send_header(k, v)
            if not has_cors:
                self._send_cors_headers()

            encoded_body = resp_body.encode("utf-8")
            self.send_header("Content-Length", str(len(encoded_body)))
            self.end_headers()
            self.wfile.write(encoded_body)

        except Exception as e:
            err_payload = json.dumps({"error": {"message": str(e)}}).encode("utf-8")
            self.send_response(500)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err_payload)))
            self.end_headers()
            self.wfile.write(err_payload)

    def log_message(self, msg_format: str, *args: Any) -> None:
        print(f"[API] {self.command} {self.path} - {args[1] if len(args) > 1 else ''}")


def background_queue_worker() -> None:
    """Continuously poll local SQS queues and invoke queue consumers."""
    sqs = boto3.client(
        "sqs",
        region_name="ap-south-1",
        endpoint_url=os.getenv("SQS_ENDPOINT_URL", "http://127.0.0.1:4566"),
    )
    ddb = boto3.resource(
        "dynamodb",
        region_name="ap-south-1",
        endpoint_url=os.getenv("DDB_ENDPOINT_URL", "http://127.0.0.1:4566"),
    )
    s3 = boto3.client(
        "s3",
        region_name="ap-south-1",
        endpoint_url=os.getenv("S3_ENDPOINT_URL", "http://127.0.0.1:4566"),
    )

    jobs_url = os.getenv("JOBS_QUEUE_URL", "")
    status_url = os.getenv("STATUS_QUEUE_URL", "")
    data_bucket = os.getenv("DATA_BUCKET", "cloudtrain-local-data")
    ds_table = os.getenv("DATASETS_TABLE", "cloudtrain-local-datasets")

    print("[Worker] Background worker started for SQS queues and S3 uploads...")

    while True:
        try:
            # 1. Poll Jobs Queue
            if jobs_url:
                res = sqs.receive_message(
                    QueueUrl=jobs_url,
                    MaxNumberOfMessages=5,
                    WaitTimeSeconds=2,
                )
                messages = res.get("Messages", [])
                if messages:
                    records = []
                    for m in messages:
                        records.append(
                            {
                                "messageId": m["MessageId"],
                                "receiptHandle": m["ReceiptHandle"],
                                "body": m["Body"],
                            }
                        )
                    print(f"[Worker] Dispatching {len(records)} job(s) to job_launcher...")
                    result = launcher_handler({"Records": records}, None)
                    failed = {item["itemIdentifier"] for item in result.get("batchItemFailures", [])}
                    for m in messages:
                        if m["MessageId"] in failed:
                            continue
                        with contextlib.suppress(Exception):
                            sqs.delete_message(
                                QueueUrl=jobs_url,
                                ReceiptHandle=m["ReceiptHandle"],
                            )

            # 2. Poll Status Queue
            if status_url:
                res = sqs.receive_message(
                    QueueUrl=status_url,
                    MaxNumberOfMessages=10,
                    WaitTimeSeconds=1,
                )
                messages = res.get("Messages", [])
                if messages:
                    records = []
                    for m in messages:
                        records.append(
                            {
                                "messageId": m["MessageId"],
                                "receiptHandle": m["ReceiptHandle"],
                                "body": m["Body"],
                            }
                        )
                    result = status_handler({"Records": records}, None)
                    failed = {item["itemIdentifier"] for item in result.get("batchItemFailures", [])}
                    for m in messages:
                        if m["MessageId"] in failed:
                            continue
                        with contextlib.suppress(Exception):
                            sqs.delete_message(
                                QueueUrl=status_url,
                                ReceiptHandle=m["ReceiptHandle"],
                            )

            # 3. Check for newly uploaded S3 datasets needing profiling
            try:
                table = ddb.Table(ds_table)
                scan_res = table.scan()
                for item in scan_res.get("Items", []):
                    if item.get("status") == "PENDING_UPLOAD":
                        s3_key = item.get("s3_key")
                        if s3_key:
                            try:
                                s3.head_object(Bucket=data_bucket, Key=s3_key)
                                print(
                                    f"[Worker] Detected uploaded dataset at s3://{data_bucket}/{s3_key}; profiling..."
                                )
                                profiler_handler(
                                    {
                                        "Records": [
                                            {
                                                "s3": {
                                                    "bucket": {"name": data_bucket},
                                                    "object": {"key": s3_key},
                                                }
                                            }
                                        ]
                                    },
                                    None,
                                )
                            except Exception:
                                pass
            except Exception:
                pass

            time.sleep(2)
        except Exception:
            time.sleep(2)


def start_server(port: int = 8000) -> None:
    if os.environ.get("ENV") != "local":
        raise RuntimeError("The development server may only run with ENV=local")
    # 1. Start embedded Moto cloud emulator if port 4566 is not running
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    endpoint = os.environ["AWS_ENDPOINT_URL"]
    parsed = urllib.parse.urlparse(endpoint)
    is_open = s.connect_ex((parsed.hostname, parsed.port or 4566)) == 0
    s.close()

    if not is_open:
        if parsed.hostname not in ("localhost", "127.0.0.1"):
            raise RuntimeError(f"Cloud emulator is unavailable at {endpoint}")
        print("[Cloud Emulator] Starting embedded Moto server on http://127.0.0.1:4566...")
        moto_server = ThreadedMotoServer(ip_address="127.0.0.1", port=4566)
        moto_server.start()
        time.sleep(1)

    # 2. Bootstrap local S3 buckets, SQS queues, and DynamoDB tables
    print("[Bootstrap] Initializing S3 bucket, DynamoDB tables, and SQS queues...")
    bootstrap_local_resources(endpoint, os.environ["AWS_REGION"])
    sqs = boto3.client("sqs", endpoint_url=os.environ["SQS_ENDPOINT_URL"])
    for variable, name in (("JOBS_QUEUE_URL", "jobs"), ("STATUS_QUEUE_URL", "status")):
        os.environ[variable] = sqs.get_queue_url(QueueName=f"cloudtrain-local-{name}")["QueueUrl"]

    # 3. Start background worker thread
    worker_thread = threading.Thread(target=background_queue_worker, daemon=True)
    worker_thread.start()

    # 4. Start HTTP Server
    server_address = ("", port)
    httpd = HTTPServer(server_address, CloudTrainHttpHandler)
    print("\n=======================================================")
    print(f"[START] CloudTrain Local Server running at http://localhost:{port}")
    print("   Cloud Emulator (S3, DDB, SQS): http://127.0.0.1:4566")
    print("   Auth Bypass: Active (local guest requests accepted)")
    print("=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down CloudTrain Local Server...")
        httpd.server_close()


if __name__ == "__main__":
    start_server()
