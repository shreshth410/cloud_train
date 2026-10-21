"""Compute backend abstraction for CloudTrain job launcher.

Provides Ec2Backend for AWS on-demand EC2 provisioning and
LocalDockerBackend for local workstation / emulator execution.
"""

import base64
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import boto3
from botocore.exceptions import ClientError

from common.logging import get_logger

logger = get_logger("compute")


@dataclass
class LaunchResult:
    """Result of compute provisioning."""

    instance_id: str
    instance_type: str
    started_at: str


class RetryableLaunchError(Exception):
    """Temporary AWS resource constraint (e.g. InsufficientInstanceCapacity, VcpuLimitExceeded)."""

    pass


class NonRetryableLaunchError(Exception):
    """Permanent error preventing EC2 launch (e.g. InvalidParameterValue, UnauthorizedOperation)."""

    pass


class ComputeBackend(Protocol):
    """Interface for compute launching and termination."""

    def launch(self, job: dict[str, Any], config: dict[str, Any]) -> LaunchResult:
        """Provision and launch trainer for a job."""
        ...

    def terminate(self, instance_id: str) -> None:
        """Terminate a running compute instance."""
        ...


def render_user_data(
    job_id: str,
    user_id: str,
    region: str,
    data_bucket: str,
    status_queue_url: str,
    trainer_image: str,
    max_runtime_seconds: int,
    log_group: str,
) -> str:
    """Render bash user-data template per SPEC Section 11.3."""
    script = f"""#!/bin/bash
set -uo pipefail
exec > >(tee -a /var/log/cloudtrain-bootstrap.log) 2>&1

export JOB_ID="{job_id}"
export USER_ID="{user_id}"
export AWS_REGION="{region}"
export DATA_BUCKET="{data_bucket}"
export STATUS_QUEUE_URL="{status_queue_url}"
export IMAGE="{trainer_image}"
export ECR_REGISTRY="${{IMAGE%%/*}}"
export MAX_RUNTIME_SECONDS="{max_runtime_seconds}"
export LOG_GROUP="{log_group}"

send_status() {{
  aws sqs send-message --region "$AWS_REGION" --queue-url "$STATUS_QUEUE_URL" --message-body \
   "{{\\"job_id\\":\\"$JOB_ID\\",\\"seq\\":0,\\"ts\\":\\"$(date -u +%FT%TZ)\\",\\"event\\":\\"$1\\",\\"status\\":\\"$2\\",\\"stage\\":\\"$3\\",\\"progress\\":0,\\"message\\":\\"$4\\",\\"payload\\":{{\\"error\\":{{\\"code\\":\\"BOOTSTRAP_FAILED\\",\\"message\\":\\"$4\\"}}}}}}" || true
}}
trap 'shutdown -h now' EXIT

dnf install -y docker || {{ send_status FAILED FAILED BOOTSTRAP "docker install failed"; exit 1; }}
systemctl enable --now docker
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY" \
  || {{ send_status FAILED FAILED BOOTSTRAP "ECR login failed"; exit 1; }}
docker pull "$IMAGE" || {{ send_status FAILED FAILED BOOTSTRAP "image pull failed"; exit 1; }}

docker run --rm --name trainer \
  --log-driver=awslogs --log-opt awslogs-region="$AWS_REGION" \
  --log-opt awslogs-group="$LOG_GROUP" --log-opt awslogs-stream="$JOB_ID" \
  -e JOB_ID -e USER_ID -e AWS_REGION -e DATA_BUCKET -e STATUS_QUEUE_URL -e MAX_RUNTIME_SECONDS \
  "$IMAGE"
exit $?
"""
    return script


class Ec2Backend:
    """Provisions on-demand EC2 instances via Launch Template."""

    def __init__(self) -> None:
        self.region = os.getenv("AWS_REGION", "ap-south-1")
        self.launch_template_id = os.getenv("LAUNCH_TEMPLATE_ID", "")
        self.data_bucket = os.getenv("DATA_BUCKET", "")
        self.status_queue_url = os.getenv("STATUS_QUEUE_URL", "")
        self.trainer_image = os.getenv("TRAINER_IMAGE_URI", "")
        self.log_group = os.getenv("TRAINING_LOG_GROUP", "/cloudtrain/dev/training")
        self.instance_type_small = os.getenv("INSTANCE_TYPE_SMALL", "t3.small")
        self.instance_type_medium = os.getenv("INSTANCE_TYPE_MEDIUM", "t3.medium")

        subnets_env = os.getenv("SUBNET_IDS", "")
        self.subnet_ids = [s.strip() for s in subnets_env.split(",") if s.strip()]

    def launch(self, job: dict[str, Any], config: dict[str, Any]) -> LaunchResult:
        """Launch an EC2 trainer instance using launch template."""
        ec2 = boto3.client("ec2", region_name=self.region)
        job_id = job["job_id"]
        user_id = job["user_id"]

        compute_size = config.get("compute", {}).get("size", "small")
        instance_type = self.instance_type_medium if compute_size == "medium" else self.instance_type_small
        max_runtime_mins = config.get("max_runtime_minutes", 30)
        max_runtime_secs = int(max_runtime_mins * 60)

        raw_script = render_user_data(
            job_id=job_id,
            user_id=user_id,
            region=self.region,
            data_bucket=self.data_bucket,
            status_queue_url=self.status_queue_url,
            trainer_image=self.trainer_image,
            max_runtime_seconds=max_runtime_secs,
            log_group=self.log_group,
        )
        b64_user_data = base64.b64encode(raw_script.encode("utf-8")).decode("utf-8")

        # Select subnet (try first, fallback to second if capacity error)
        subnets_to_try = self.subnet_ids if self.subnet_ids else [None]

        last_error = None
        for subnet_id in subnets_to_try:
            run_kwargs: dict[str, Any] = {
                "ClientToken": job_id,
                "InstanceType": instance_type,
                "UserData": b64_user_data,
                "MinCount": 1,
                "MaxCount": 1,
                "TagSpecifications": [
                    {
                        "ResourceType": "instance",
                        "Tags": [
                            {"Key": "Project", "Value": "cloudtrain"},
                            {"Key": "Role", "Value": "trainer"},
                            {"Key": "JobId", "Value": job_id},
                            {"Key": "UserId", "Value": user_id},
                        ],
                    }
                ],
            }

            if self.launch_template_id:
                run_kwargs["LaunchTemplate"] = {"LaunchTemplateId": self.launch_template_id}
            if subnet_id:
                run_kwargs["SubnetId"] = subnet_id

            try:
                logger.info(f"Calling RunInstances for job {job_id} (type={instance_type}, subnet={subnet_id})...")
                resp = ec2.run_instances(**run_kwargs)
                instances = resp.get("Instances", [])
                if not instances:
                    raise NonRetryableLaunchError("RunInstances returned empty instance list.")

                instance_id = instances[0]["InstanceId"]
                started_at = datetime.now(UTC).isoformat()
                logger.info(f"Successfully launched EC2 instance {instance_id} for job {job_id}")
                return LaunchResult(
                    instance_id=instance_id,
                    instance_type=instance_type,
                    started_at=started_at,
                )
            except ClientError as e:
                err_code = e.response["Error"]["Code"]
                logger.warning(f"EC2 RunInstances failed on subnet {subnet_id}: {err_code} - {e}")
                last_error = e
                if err_code in ("InsufficientInstanceCapacity", "RequestLimitExceeded", "VcpuLimitExceeded"):
                    # Try next subnet if available
                    continue
                else:
                    raise NonRetryableLaunchError(f"EC2 non-retryable error: {err_code} - {e}") from e

        # All subnets exhausted or retryable error hit
        if last_error:
            err_code = last_error.response["Error"]["Code"]
            if err_code in ("InsufficientInstanceCapacity", "RequestLimitExceeded", "VcpuLimitExceeded"):
                raise RetryableLaunchError(f"Temporary capacity error: {err_code}") from last_error
            raise NonRetryableLaunchError(f"Permanent launch error: {last_error}") from last_error

        raise NonRetryableLaunchError("Failed to launch EC2 instance.")

    def terminate(self, instance_id: str) -> None:
        """Terminate EC2 instance."""
        if not instance_id:
            return
        ec2 = boto3.client("ec2", region_name=self.region)
        try:
            logger.info(f"Terminating EC2 instance {instance_id}")
            ec2.terminate_instances(InstanceIds=[instance_id])
        except Exception as e:
            logger.warning(f"Failed to terminate instance {instance_id}: {e}")


class LocalDockerBackend:
    """Runs training container locally via Docker or mocks for testing."""

    def __init__(self) -> None:
        self.image = os.getenv("TRAINER_IMAGE_URI", "cloudtrain-trainer:latest")
        self.data_bucket = os.getenv("DATA_BUCKET", "cloudtrain-dev-data")
        self.status_queue_url = os.getenv("STATUS_QUEUE_URL", "")
        self.s3_endpoint_url = os.getenv("S3_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL", "")
        self.sqs_endpoint_url = os.getenv("SQS_ENDPOINT_URL") or os.getenv("AWS_ENDPOINT_URL", "")

    def launch(self, job: dict[str, Any], config: dict[str, Any]) -> LaunchResult:
        """Launch local container."""
        job_id = job["job_id"]
        user_id = job["user_id"]
        max_runtime_mins = config.get("max_runtime_minutes", 30)

        container_name = f"trainer-{job_id}"
        instance_id = f"local-{job_id}"
        started_at = datetime.now(UTC).isoformat()

        has_docker_image = False
        try:
            check = subprocess.run(
                ["docker", "image", "inspect", self.image],
                capture_output=True,
                timeout=2,
            )
            if check.returncode == 0:
                has_docker_image = True
        except Exception:
            has_docker_image = False

        if has_docker_image:
            cmd = [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                container_name,
                "-e",
                f"JOB_ID={job_id}",
                "-e",
                f"USER_ID={user_id}",
                "-e",
                f"DATA_BUCKET={self.data_bucket}",
                "-e",
                f"STATUS_QUEUE_URL={self.status_queue_url}",
                "-e",
                f"MAX_RUNTIME_SECONDS={int(max_runtime_mins * 60)}",
            ]
            if self.s3_endpoint_url:
                cmd.extend(["-e", f"S3_ENDPOINT_URL={self.s3_endpoint_url}"])
            if self.sqs_endpoint_url:
                cmd.extend(["-e", f"SQS_ENDPOINT_URL={self.sqs_endpoint_url}"])

            cmd.extend(["--network", os.getenv("LOCAL_DOCKER_NETWORK", "host")])
            for name in ("AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
                cmd.extend(["-e", f"{name}={os.getenv(name, 'test' if 'KEY' in name else 'ap-south-1')}"])
            cmd.append(self.image)

            try:
                logger.info(f"Starting local container for job {job_id}: {' '.join(cmd)}")
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
            except Exception as e:
                raise NonRetryableLaunchError(f"Could not start trainer container: {e}") from e
        else:
            if os.getenv("LOCAL_REQUIRE_DOCKER") == "1":
                raise NonRetryableLaunchError(
                    f"Trainer image {self.image} is unavailable; build the trainer service first."
                )
            logger.info(f"Docker image {self.image} not cached; running local Python trainer process for job {job_id}")
            env = os.environ.copy()
            env.update(
                {
                    "JOB_ID": job_id,
                    "USER_ID": user_id,
                    "DATA_BUCKET": self.data_bucket,
                    "STATUS_QUEUE_URL": self.status_queue_url,
                    "MAX_RUNTIME_SECONDS": str(int(max_runtime_mins * 60)),
                }
            )
            if self.s3_endpoint_url:
                env["S3_ENDPOINT_URL"] = self.s3_endpoint_url
            if self.sqs_endpoint_url:
                env["SQS_ENDPOINT_URL"] = self.sqs_endpoint_url

            subprocess.Popen([sys.executable, "-m", "cloudtrain_trainer.main"], env=env)

        return LaunchResult(
            instance_id=instance_id,
            instance_type="local.docker",
            started_at=started_at,
        )

    def terminate(self, instance_id: str) -> None:
        """Stop local container."""
        job_id = instance_id.replace("local-", "")
        container_name = f"trainer-{job_id}"
        try:
            subprocess.run(["docker", "stop", container_name], capture_output=True, timeout=5)
        except Exception as e:
            logger.warning(f"Could not stop local container {container_name}: {e}")


def get_compute_backend() -> ComputeBackend:
    """Factory returning configured ComputeBackend implementation."""
    backend_type = os.getenv("COMPUTE_BACKEND", "ec2").lower()
    if backend_type == "local":
        return LocalDockerBackend()
    return Ec2Backend()
