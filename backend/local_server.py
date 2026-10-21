#!/usr/bin/env python3
"""Local HTTP API Server & Event Dispatcher for CloudTrain.

Listens on http://localhost:8000. Translates HTTP requests to API Gateway v2
events and routes them to backend/api/main.py:lambda_handler. Also runs a
background thread polling local SQS queues (LocalStack) to invoke job_launcher
and status_updater.
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

# Default environment configuration for LocalStack
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("DDB_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("SQS_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("LOCAL_AUTH_BYPASS", "1")
os.environ.setdefault("COMPUTE_BACKEND", "local")
os.environ.setdefault("DATA_BUCKET", "cloudtrain-local-data")
os.environ.setdefault("JOBS_TABLE", "cloudtrain-local-jobs")
os.environ.setdefault("DATASETS_TABLE", "cloudtrain-local-datasets")
os.environ.setdefault("JOBS_QUEUE_URL", "http://localhost:4566/000000000000/cloudtrain-local-jobs")
os.environ.setdefault("STATUS_QUEUE_URL", "http://localhost:4566/000000000000/cloudtrain-local-status")
os.environ.setdefault("TRAINER_IMAGE_URI", "cloudtrain-trainer:latest")
os.environ.setdefault("MAX_CONCURRENT_INSTANCES", "2")
os.environ.setdefault("CORS_ALLOW_ORIGIN", "*")

import boto3  # noqa: E402

from api.main import lambda_handler as api_handler  # noqa: E402
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
            for k, v in resp_headers.items():
                self.send_header(k, v)
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
        # Clean logging
        print(f"[API] {self.command} {self.path} - {args[1] if len(args) > 1 else ''}")


def background_queue_worker() -> None:
    """Continuously poll local SQS queues and invoke queue consumers."""
    sqs = boto3.client(
        "sqs",
        region_name="ap-south-1",
        endpoint_url=os.getenv("SQS_ENDPOINT_URL", "http://localhost:4566"),
    )
    jobs_url = os.getenv("JOBS_QUEUE_URL", "")
    status_url = os.getenv("STATUS_QUEUE_URL", "")

    print("[Worker] Started background SQS queue dispatcher against LocalStack...")

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
                    launcher_handler({"Records": records}, None)
                    for m in messages:
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
                    status_handler({"Records": records}, None)
                    for m in messages:
                        with contextlib.suppress(Exception):
                            sqs.delete_message(
                                QueueUrl=status_url,
                                ReceiptHandle=m["ReceiptHandle"],
                            )

        except Exception:
            # SQS queue might not be ready yet
            time.sleep(3)


def start_server(port: int = 8000) -> None:
    worker_thread = threading.Thread(target=background_queue_worker, daemon=True)
    worker_thread.start()

    server_address = ("", port)
    httpd = HTTPServer(server_address, CloudTrainHttpHandler)
    print("\n=======================================================")
    print(f"🚀 CloudTrain Local Server running at http://localhost:{port}")
    print(f"   Connected to LocalStack at {os.getenv('AWS_ENDPOINT_URL')}")
    print("   Auth Bypass enabled: local guest requests accepted")
    print("=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down CloudTrain Local Server...")
        httpd.server_close()


if __name__ == "__main__":
    start_server()
