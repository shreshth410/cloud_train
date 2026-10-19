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
