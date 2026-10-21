# CloudTrain — Zero-Cost Cloud & Local ML Training Platform

> A no-code, cloud-native automated machine learning (AutoML) platform modeled after AWS SageMaker Canvas. Upload CSV datasets, configure features and hyperparameters through an interactive wizard, dispatch asynchronous training jobs, and download trained model bundles with rich evaluation metrics.

---

## Architecture & Cloud Concepts

CloudTrain is architected around decoupled cloud computing patterns (IaaS, PaaS, and FaaS) designed to run within the **AWS Free Tier** or **100% locally with zero cloud costs** via embedded emulation.

| Cloud Service | Role in CloudTrain | Local Emulation (Zero-Cost) |
| :--- | :--- | :--- |
| **Amazon S3** | Object storage for raw datasets, model artifacts (`model.joblib`), evaluation metrics, and training logs | Moto S3 / Path-style bucket (`cloudtrain-local-data`) |
| **Amazon DynamoDB** | NoSQL database for dataset metadata, job states, and atomic capacity slots (`__capacity__`) | Moto DynamoDB tables (`cloudtrain-local-jobs`, `cloudtrain-local-datasets`) |
| **Amazon SQS** | Decoupled message queues for asynchronous job scheduling (`jobs-queue`) and real-time status events (`status-queue`) | Moto SQS queues with long-polling worker dispatcher |
| **Amazon EC2 / Docker** | Isolated compute instances running containerized ML training pipelines (`scikit-learn`, `pandas`) | Local Docker containers (`cloudtrain-trainer`) or native Python processes |
| **AWS Lambda / API Gateway** | Serverless REST API endpoints for user authentication, presigned URLs, quotas, and job controls | Python HTTP API Gateway translator (`backend/local_server.py`) or Nginx proxy |
| **AWS Cognito** | JWT-based user identity, authentication, and quotas | Local guest bypass mode (`LOCAL_AUTH_BYPASS=1`) |

```
                       ┌─────────────────────────────────────────┐
                       │          React Frontend (Vite)          │
                       │          http://localhost:5173          │
                       └───────────────────┬─────────────────────┘
                                           │
                        REST API / Presigned POST Uploads
                                           │
                                           ▼
                       ┌─────────────────────────────────────────┐
                       │   API Gateway / Translator (:8000)      │
                       └───────────┬─────────────────┬───────────┘
                                   │                 │
                           Write Metadata     Enqueue Job Message
                                   │                 │
                                   ▼                 ▼
                         ┌────────────────┐   ┌────────────────┐
                         │    DynamoDB    │   │ SQS Jobs Queue │
                         └────────────────┘   └───────┬────────┘
                                                      │ Worker Polls
                                                      ▼
                                           ┌──────────────────────┐
                                           │ Atomic Slot Acquired │ (Max Concurrent: 2)
                                           └──────────┬───────────┘
                                                      │
                                                      ▼
                                           ┌──────────────────────┐
                                           │ ML Trainer Runtime   │
                                           │ (Docker / Subprocess)│
                                           └──────────┬───────────┘
                                                      │
                                                      │ Streams progress & metrics
                                                      ▼
                                           ┌──────────────────────┐
                                           │   SQS Status Queue   │
                                           └──────────┬───────────┘
                                                      │ Updates Job State
                                                      ▼
                                           ┌──────────────────────┐
                                           │    DynamoDB Table    │
                                           │  Status: SUCCEEDED   │
                                           └──────────────────────┘
```

---

## Quick Start: Running Locally

You can run CloudTrain locally using either **Docker Compose** (recommended for presentations and containerized demos) or **Native Terminals** (fast Python & Vite processes).

### Option 1: Docker Compose (Recommended)

Runs all four services (Frontend Nginx, Python Backend API, Moto Cloud Emulator, and ML Trainer) in isolated containers:

```powershell
# 1. Start all containerized services
docker compose -f docker-compose.local.yml up --build

# 2. Open the web application
# 👉 http://localhost:5173

# 3. When finished, shut down containers
docker compose -f docker-compose.local.yml down
```

---

### Option 2: Native Terminals (Direct Python & Node)

If you prefer running directly in separate terminal tabs with live logs:

#### **Terminal 1: Backend & Cloud Emulator**
```powershell
cd d:\codes\ccd_project
.\.venv\Scripts\python backend/local_server.py
```
> Starts the embedded Moto cloud emulator (S3, DynamoDB, SQS on port `4566`), auto-provisions buckets/tables, and boots the CloudTrain API Gateway on `http://localhost:8000`.

#### **Terminal 2: Frontend Dev Server**
```powershell
cd d:\codes\ccd_project\frontend
npm run dev
```
> Boots Vite with Hot Module Replacement on `http://localhost:5173`.

---

## Step-by-Step Presentation & Demo Flow

### 1. Upload & Profile a Dataset
1. Navigate to **Datasets** (`http://localhost:5173/datasets`).
2. Click **Upload Dataset** and select [samples/iris.csv](samples/iris.csv) or [samples/diabetes.csv](samples/diabetes.csv).
3. **What happens under the hood:**
   - The browser requests an S3 **Presigned POST URL** from the backend.
   - The CSV is streamed directly to S3 (`cloudtrain-local-data`).
   - S3 triggers an asynchronous profiler that scans column types, missing value percentages, distributions, and generates summary statistics.
   - The dataset status transitions from `PENDING_UPLOAD` ➔ `PROCESSING` ➔ `READY`.

### 2. Configure & Train an ML Model
1. Navigate to **Train Model** (`http://localhost:5173/train`).
2. **Step 1 — Dataset:** Select your uploaded dataset (`iris.csv`).
3. **Step 2 — Target & Features:** Select target column (`target`), select feature columns.
4. **Step 3 — Model Selection:** Choose an algorithm:
   - **Classification:** Random Forest, Logistic Regression, Support Vector Machine (SVC), Decision Tree.
   - **Regression:** Random Forest Regressor, Ridge Regression, Linear Regression.
5. **Step 4 — Hyperparameters:** Configure estimators, max depth, learning rate, and cross-validation folds.
6. Click **Start Training**.

### 3. Asynchronous Job Execution & Concurrency
- The API Gateway responds with `202 Accepted` in milliseconds and dispatches a message into the **SQS Jobs Queue**.
- The worker verifies available capacity in DynamoDB (`__capacity__`, max 2 concurrent instances).
- The compute backend launches the training pipeline.
- Real-time progress is published to the **SQS Status Queue**:
  `QUEUED` ➔ `PROVISIONING` ➔ `RUNNING (5% Bootstrap ➔ 10% Downloading ➔ 50% Fitting ➔ 90% Evaluating)` ➔ `SUCCEEDED (100%)`.
- If multiple jobs are submitted simultaneously, excess jobs wait safely in SQS and automatically begin execution when a running job finishes.

### 4. Inspect Results & Download Model
1. Open the job details page (`/jobs/{id}`).
2. Inspect:
   - **Evaluation Metrics:** Accuracy, F1 Score, Precision, Recall, Confusion Matrix, and ROC Curves.
   - **Feature Importance:** Top predictive features ranked by importance.
   - **Live Training Logs:** Real-time log stream stored in S3 (`logs.txt`).
   - **Artifact Download:** Download the portable `model.joblib` artifact.

---

## Repository Structure

```
ccd_project/
├── backend/                  # Python API Gateway & Lambda Services
│   ├── api/                  # REST API handlers (routes for /datasets, /jobs, /models, /me)
│   ├── dataset_profiler/     # SQS consumer that auto-profiles uploaded CSVs
│   ├── job_launcher/         # SQS consumer that handles capacity slots & compute launches
│   ├── status_updater/       # SQS consumer that writes state transitions to DynamoDB
│   ├── local_server.py       # Local development server with embedded Moto emulator
│   └── Dockerfile.local      # Container definition for local backend & emulator
├── frontend/                 # React 18 + TypeScript + Vite SPA
│   ├── src/pages/            # Dashboard, Datasets, Wizard, Jobs, JobDetail
│   ├── src/lib/api.ts        # Typed API client, presigned S3 upload handler
│   ├── nginx.local.conf      # Reverse proxy configuration for Docker container
│   └── Dockerfile            # Multi-stage production build container
├── trainer/                  # Standalone ML training pipeline container
│   ├── cloudtrain_trainer/   # Scikit-learn models, preprocessing, metrics & S3 uploader
│   └── Dockerfile            # Hardened non-root training image
├── infra/                    # Terraform configurations for production AWS deployment
│   ├── modules/              # s3, dynamodb, sqs, lambda, ec2, cognito, cloudfront
│   └── environments/         # dev / prod variables
├── samples/                  # Sample CSVs (iris.csv, diabetes.csv)
├── scripts/                  # Bootstrap and testing scripts
└── docker-compose.local.yml  # Multi-container local orchestration
```

---

## Production AWS Deployment (Terraform)

For full deployment to real AWS infrastructure:

```bash
# 1. Authenticate with AWS CLI
aws configure

# 2. Initialize and deploy infrastructure via Terraform
cd infra/environments/dev
terraform init
terraform plan
terraform apply
```

To tear down all cloud infrastructure and prevent any unexpected charges:
```bash
terraform destroy
```

---

## Coursework & Academic Attribution

This project was built for educational purposes as part of the **Cloud Computing (CCD)** curriculum to demonstrate:
- **IaaS vs. PaaS vs. FaaS:** Combining containerized compute (EC2/Docker), managed NoSQL and object stores (DynamoDB/S3), and serverless event-driven dispatchers (Lambda/SQS).
- **FinOps & Resource Limiting:** Enforcing strict concurrency quotas to prevent cloud cost overruns.
- **Microservices & Queue Decoupling:** Event-driven architecture where HTTP APIs never block on heavy ML computational workloads.
