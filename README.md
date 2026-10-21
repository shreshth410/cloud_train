# CloudTrain

> A no-code, cloud-based ML model training platform on AWS.

## Overview

CloudTrain is a mini "SageMaker Canvas": a web app where a signed-in user uploads a CSV dataset, clicks through a wizard (target column → features → model → hyperparameters → compute size), presses **Train**, watches the job progress, and downloads the trained model with its metrics.

## Architecture

- **Auth:** AWS Cognito (sign-up/sign-in)
- **Storage:** S3 (datasets, artifacts), DynamoDB (metadata)
- **Compute:** On-demand EC2 instances running Docker containers
- **Orchestration:** SQS queues with Lambda consumers
- **Frontend:** React SPA served via CloudFront
- **Infrastructure:** Terraform, deployed by GitHub Actions with OIDC

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20 LTS
- Docker ≥ 24
- Terraform ≥ 1.10
- AWS CLI v2

### Local Development

```bash
make setup          # Install dependencies
make lint           # Run linters
make test           # Run tests
make local-up       # Start local emulator stack
make e2e-local      # Run end-to-end tests locally
make local-down     # Stop local stack
```

### AWS Deployment

See `docs/RUNBOOK.md` for full deployment instructions.

## Cost Notes

This project is designed to run within the AWS Free Plan. See `docs/COST.md` for detailed cost analysis.

## Teardown

```bash
make destroy        # Destroy all AWS resources
make panic          # Emergency: terminate all instances + disable queues
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Cost Analysis](docs/COST.md)
- [Runbook](docs/RUNBOOK.md)
- [Demo Script](docs/DEMO_SCRIPT.md)
- [Decisions Log](docs/DECISIONS.md)

## License

This project is for educational purposes as part of a cloud computing course.

### Run the whole application with Docker Desktop

From the repository root (PowerShell or a terminal):

```sh
docker compose -f docker-compose.local.yml up --build -d
```

Open **http://localhost:5173** and upload `samples/iris.csv`. Wait for READY,
open the training wizard, choose `target` and Random Forest, then train.
For regression, use `samples/diabetes.csv` with Ridge. Results include metrics,
logs and downloadable model files. Each job runs in its own trainer container.

The stack includes the built React website served by nginx, the Python API and
queue dispatcher, Moto (S3/SQS/DynamoDB emulation), and the trainer image. It
requires no AWS account or LocalStack token. The website uses `/api` through
nginx; signed uploads and downloads use `http://localhost:4566`. All published
ports bind to this computer only. Local authentication is a development bypass;
use the Terraform/Cognito deployment for public access.

Moto data is in memory and is lost when the emulator restarts. Download wanted
models before stopping. The backend mounts Docker's socket to launch trainers.
The old LocalStack volume is not removed by this configuration.

```sh
# Inspect services and errors
docker compose -f docker-compose.local.yml ps
docker compose -f docker-compose.local.yml logs --tail=100 backend emulator
# Test real HTTP uploads, profiling, classification/regression, logs and downloads
python scripts/e2e_docker.py
# Stop the local services
docker compose -f docker-compose.local.yml down
```

The HTTP smoke test needs `requests` installed in the selected Python environment
(`python -m pip install requests`). The existing `e2e_smoke.py --local` is an
in-process mock test; it does not test the Docker network or browser upload URL.

If you still see “Failed to fetch”, rebuild with the command above, reload the
page, and check that frontend/backend/emulator are healthy. The API must be
reachable at http://localhost:5173/api/models. Close an old host development
server if Docker reports port 5173, 8000, or 4566 already in use.
