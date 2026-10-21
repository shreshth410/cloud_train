"""Regression tests for the local HTTP transport and browser upload URLs."""

import os
import subprocess
import sys
from pathlib import Path


def test_http_response_has_status_line():
    # Import local_server in a child so its development defaults cannot leak into unit tests.
    script = """
import http.client
import threading
from http.server import HTTPServer
import local_server
local_server.api_handler = lambda event, context: {"statusCode": 201, "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}, "body": '{"dataset_id":"test"}'}
server = HTTPServer(("127.0.0.1", 0), local_server.CloudTrainHttpHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
    connection.request("POST", "/datasets", body='{}', headers={"Content-Type": "application/json"})
    response = connection.getresponse()
    assert response.status == 201
    assert response.getheader("Access-Control-Allow-Origin") == "*"
    assert response.read() == b'{"dataset_id":"test"}'
finally:
    server.shutdown()
    server.server_close()
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    subprocess.run([sys.executable, "-c", script], env=env, check=True, timeout=15)


def test_presigned_urls_use_public_endpoint(monkeypatch):
    from common.s3 import generate_presigned_download, generate_presigned_upload, get_s3_client

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://emulator:4566")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT_URL", "http://localhost:4566")
    assert get_s3_client().meta.endpoint_url == "http://emulator:4566"
    assert generate_presigned_upload("bucket", "data.csv")["url"].startswith("http://localhost:4566/")
    assert generate_presigned_download("bucket", "model.joblib").startswith("http://localhost:4566/")


def test_docker_launch_uses_network_and_credentials(monkeypatch):
    from types import SimpleNamespace

    from job_launcher.compute import LocalDockerBackend

    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("job_launcher.compute.subprocess.run", run)
    monkeypatch.setenv("LOCAL_DOCKER_NETWORK", "cloudtrain-local")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://emulator:4566")
    LocalDockerBackend().launch({"job_id": "j", "user_id": "u"}, {})
    command = calls[-1]
    assert command[command.index("--network") + 1] == "cloudtrain-local"
    assert "AWS_ACCESS_KEY_ID=test" in command
    assert "S3_ENDPOINT_URL=http://emulator:4566" in command


def test_docker_launch_failure_is_not_reported_as_success(monkeypatch):
    from types import SimpleNamespace

    import pytest

    from job_launcher.compute import LocalDockerBackend, NonRetryableLaunchError

    def run(command, **kwargs):
        if command[1] == "image":
            return SimpleNamespace(returncode=0)
        raise subprocess.CalledProcessError(125, command)

    monkeypatch.setattr("job_launcher.compute.subprocess.run", run)
    with pytest.raises(NonRetryableLaunchError):
        LocalDockerBackend().launch({"job_id": "j", "user_id": "u"}, {})
