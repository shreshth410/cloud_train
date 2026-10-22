# CloudTrain — Master Project Guide & Technical Dossier
> **Platform:** CloudTrain (Zero-Cost Cloud & Local ML Training Platform)  
> **Course:** Cloud Computing (CCD) / Distributed Systems  
> **Target Audience:** Professor Presentation, Technical Viva, and Architecture Review

---

## Table of Contents
1. [Executive Summary & The "Elevator Pitch"](#1-executive-summary--the-elevator-pitch)
2. [End-to-End System Architecture](#2-end-to-end-system-architecture)
3. [Deep-Dive: End-to-End Flow of Requests](#3-deep-dive-end-to-end-flow-of-requests)
   - [Flow A: Dataset Ingestion & Profiling](#flow-a-dataset-ingestion--profiling)
   - [Flow B: Job Configuration & Submission](#flow-b-job-configuration--submission)
   - [Flow C: Compute Provisioning & Concurrency Control](#flow-c-compute-provisioning--concurrency-control)
   - [Flow D: Training Execution & Real-Time Telemetry](#flow-d-training-execution--real-time-telemetry)
   - [Flow E: Artifact Generation & Instance Self-Termination](#flow-e-artifact-generation--instance-self-termination)
4. [Comprehensive AWS Services Breakdown](#4-comprehensive-aws-services-breakdown)
5. [Docker Containerization (Basic & Essential Role)](#5-docker-containerization-basic--essential-role)
6. [Critical Technicalities & Distributed Systems Concepts](#6-critical-technicalities--distributed-systems-concepts)
   - [1. Monotonic State Machine & State Rank Enforcement](#1-monotonic-state-machine--state-rank-enforcement)
   - [2. Distributed Concurrency & Atomic Capacity Slots](#2-distributed-concurrency--atomic-capacity-slots)
   - [3. Asynchronous Decoupling & At-Least-Once Toleration](#3-asynchronous-decoupling--at-least-once-toleration)
   - [4. Dead-Letter Queues (DLQ) & Failure Recovery](#4-dead-letter-queues-dlq--failure-recovery)
   - [5. The Watchdog Pattern (Heartbeat & Zombie Reaper)](#5-the-watchdog-pattern-heartbeat--zombie-reaper)
   - [6. Multi-Tenant Security & Zero-Trust Isolation](#6-multi-tenant-security--zero-trust-isolation)
   - [7. FinOps & Cost-Guardrail Engineering](#7-finops--cost-guardrail-engineering)
7. [Local Emulation vs. AWS Cloud Execution](#7-local-emulation-vs-aws-cloud-execution)
8. [Professor Viva & Presentation Q&A Preparation](#8-professor-viva--presentation-qa-preparation)

---

## 1. Executive Summary & The "Elevator Pitch"

### What is CloudTrain?
**CloudTrain** is a no-code, cloud-native automated machine learning (AutoML) platform modeled after industrial cloud services like **AWS SageMaker Canvas**. It enables non-technical end users to upload tabular CSV datasets, automatically inspect and profile data quality, configure predictive models (Classification and Regression) through an interactive visual wizard, dispatch asynchronous distributed training jobs, and download serialized production-ready model bundles (`model.joblib`) accompanied by explainability reports, evaluation charts, and runnable inference code.

### Core Academic Problem Addressed
Training machine learning models in modern cloud environments typically suffers from two extremes:
1. **Managed ML Services (e.g., AWS SageMaker):** Powerful, but carry high continuous hourly baseline costs and opaque pricing, making them cost-prohibitive for small organizations, students, and research labs.
2. **Ad-Hoc Virtual Machines:** Running persistent VMs (like continuous EC2 instances or Google Colab) leads to idle resource waste, forgotten instances, security vulnerabilities from open SSH ports, and zero multi-tenant governance.

**CloudTrain solves this dilemma** by implementing a decoupled, event-driven cloud architecture engineered specifically for **Zero Idle Cost**. When no training jobs are running, the platform's infrastructure costs **$0.00**. When a job is submitted, compute resources are provisioned on-demand, run the workload in an isolated container, stream real-time telemetry, upload artifacts, and **immediately terminate themselves**.

### Key Cloud Paradigms Demonstrated
- **IaaS (Infrastructure as Service):** Ephemeral EC2 compute nodes provisioned dynamically via launch templates.
- **PaaS (Platform as a Service):** Serverless object storage (Amazon S3), managed NoSQL databases (Amazon DynamoDB), and identity management (Amazon Cognito).
- **FaaS (Function as a Service):** Event-driven serverless dispatchers and routers (AWS Lambda).
- **Queue-Decoupled Microservices:** Asynchronous job dispatching and telemetry processing using Amazon SQS standard queues and Dead Letter Queues (DLQ).
- **Infrastructure as Code (IaC):** 100% of cloud resources defined, parameterized, and deployed through Terraform and automated GitHub Actions OIDC CI/CD.

---

## 2. End-to-End System Architecture

```
                                  [ User's Web Browser ]
                               (React 18 + TypeScript SPA)
                                            │
                      ┌─────────────────────┴─────────────────────┐
                      │ 1. Direct Multipart POST                  │ 2. REST API Requests
                      │    (Presigned S3 Upload)                  │    (Bearer JWT Auth)
                      ▼                                           ▼
             ┌─────────────────┐                        ┌───────────────────┐
             │    Amazon S3    │                        │  Amazon Cognito   │
             │   Data Bucket   │                        │ (User Pool & JWT) │
             └────────┬────────┘                        └─────────┬─────────┘
                      │                                           │ Validates Claims
                      │ s3:ObjectCreated                          ▼
                      ▼                                 ┌───────────────────┐
             ┌─────────────────┐                        │  API Gateway v2   │
             │ dataset_profiler│                        │    (HTTP API)     │
             │     Lambda      │                        └─────────┬─────────┘
             └────────┬────────┘                                  │
                      │                                           ▼
                      │ Write Profile                   ┌───────────────────┐
                      │                                 │    api Lambda     │
                      │                                 │   (REST Router)   │
                      │                                 └────┬────────────┬─┘
                      │                                      │            │
                      ▼                                      │ Enqueue    │ Write Job
             ┌─────────────────┐                             ▼            ▼
             │ Amazon DynamoDB │                      ┌─────────────┐ ┌──────────────┐
             │ (Metadata/Jobs) │◄─────────────────────┤  SQS Jobs   │ │ S3 Config    │
             └────────┬────────┘  Reconciles State    │    Queue    │ │ config.json  │
                      ▲                               └──────┬──────┘ └──────────────┘
                      │                                      │
                      │ Status Updates                       ▼
                      │                              ┌──────────────┐
             ┌────────┴────────┐                     │ job_launcher │
             │ status_updater  │                     │    Lambda    │
             │     Lambda      │                     └──────┬───────┘
             └────────▲────────┘                            │ Checks atomic slot &
                      │                                     │ calls RunInstances
                      │ Reads Events                        ▼
             ┌────────┴────────┐                     ┌───────────────────────────────┐
             │   SQS Status    │                     │    Amazon EC2 Trainer Node    │
             │     Queue       │                     │ (Amazon Linux 2023 + Docker)  │
             └────────▲────────┘                     ├───────────────────────────────┤
                      │                              │ 1. Pulls image from ECR       │
                      │ Publishes Progress (seq=1..n)│ 2. Mounts env & streams logs  │
                      └──────────────────────────────┤ 3. Uploads model & metrics    │
                                                     │ 4. Executes self-shutdown     │
                                                     └──────────────┬────────────────┘
                                                                    │ S3 Artifacts
                                                                    ▼
                                                             ┌───────────────┐
                                                             │   Amazon S3   │
                                                             │  (Artifacts)  │
                                                             └───────────────┘
```

---

## 3. Deep-Dive: End-to-End Flow of Requests

Understanding the exact journey of a request through the system is critical for viva presentations. CloudTrain breaks operations into 5 discrete asynchronous flows:

### Flow A: Dataset Ingestion & Profiling
```
[Browser] ──(1) POST /datasets──> [API Gateway / Lambda] ──(2) PutItem PENDING──> [DynamoDB]
   │                                      │
   │<──(3) Presigned S3 POST Policy───────┘
   │
   └──(4) Direct HTTP POST CSV File ───────────────────────────────> [S3 Data Bucket]
                                                                            │
                                                                 (5) s3:ObjectCreated
                                                                            ▼
[DynamoDB] <──(7) Update READY/INVALID ── [dataset_profiler Lambda] <───────┘
   ▲                                              │
   └────────────── (8) Polls GET /datasets/{id} ──[Browser]
```

1. **Upload Initiation:** The user selects a `.csv` file in the UI. The frontend sends `POST /datasets` with `{ name, size_bytes }` to the API.
2. **Quota & Presigned Generation:** The `api` Lambda validates file extension and size (≤ 100 MB), ensures user hasn't exceeded dataset quotas (max 10 datasets), writes a record to the `datasets` DynamoDB table with status `PENDING_UPLOAD`, and generates an **S3 Pre-Signed POST URL** with a 15-minute expiration and a strict `content-length-range` policy.
3. **Direct-to-S3 Upload:** The browser streams the CSV payload directly to Amazon S3 using `XMLHttpRequest` with upload progress tracking. **Why this matters:** The file bypasses API Gateway and Lambda completely. This prevents API Gateway 10 MB payload limits and eliminates expensive Lambda memory/network bandwidth consumption.
4. **Automated Profiling Trigger:** Upon successful arrival in S3 at prefix `datasets/{user_id}/{dataset_id}/data.csv`, an S3 `s3:ObjectCreated` event notification immediately triggers the `dataset_profiler` Lambda asynchronously.
5. **Statistical Profiling:** The profiler streams the CSV in chunks, infers column datatypes (`numeric`, `categorical`, `boolean`, `datetime`, `id_like`, `constant`, `text`), computes missing value counts and percentages, extracts distribution statistics (mean, min, max, unique counts), detects potential data quality issues (e.g., target missing > 5%, constant columns), and samples preview rows.
6. **State Transition:** If valid, the profiler updates the dataset status in DynamoDB to `READY` with the full profile JSON. If invalid (e.g. empty file, > 500 columns, > 1,000,000 rows, corrupt encoding), it marks it `INVALID` with descriptive error reasons.
7. **Client Polling:** The frontend polls `GET /datasets/{id}` every 3 seconds until the status becomes `READY`, upon which the interactive schema and preview table are rendered.

---

### Flow B: Job Configuration & Submission
```
[Browser UI Wizard] ── POST /jobs (Config JSON) ──> [API Gateway / api Lambda]
                                                             │
                                   ┌─────────────────────────┴─────────────────────────┐
                                   ▼                                                   ▼
                       [Validate Config Schema & Quota]                    [S3 Data Bucket]
                                   │                                  Write config.json to:
                                   ├─────────────────────────────┐    jobs/{uid}/{jid}/config.json
                                   ▼                             ▼
                           [DynamoDB Jobs Table]         [SQS Jobs Queue]
                           Status: QUEUED                Message: {job_id, user_id}
                                   │                             │
                                   └──────────────┬──────────────┘
                                                  ▼
                                      Return 202 Accepted (< 2s)
```

1. **Visual Wizard Setup:** In the UI, the user selects a `READY` dataset, chooses a target column (the platform auto-detects Classification vs. Regression), selects/unselects feature columns, picks a model from the model registry, fine-tunes hyperparameters, and selects compute size (`small` vs. `medium`).
2. **Synchronous Validation:** The user clicks "Start Training", sending `POST /jobs`. The `api` Lambda:
   - Validates the payload against `shared/job_config.schema.json` and `shared/model_registry.json`.
   - Checks active job concurrency limits (max 3 active jobs per user).
   - Verifies target column validity (not constant, not an ID, missing rows ≤ 5%).
3. **Dual Persistence & Fast Return:**
   - Saves the resolved job configuration to S3 at `jobs/{user_id}/{job_id}/config.json`.
   - Writes an initial record to the DynamoDB `jobs` table with `status="QUEUED"`.
   - Sends an execution message `{ "job_id": "...", "user_id": "...", "requeue_count": 0 }` to the `cloudtrain-jobs` SQS queue.
   - Responds to the browser with **`HTTP 202 Accepted`** within ~1.5 seconds. The user never waits on compute availability!

---

### Flow C: Compute Provisioning & Concurrency Control
```
[SQS Jobs Queue] ──(1) Poll Message──> [job_launcher Lambda]
                                              │
                                              ▼
                                 [DynamoDB Atomic Check]
                                 Item: __capacity__
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      │ Slot Available (in_use < 2)                   │ Slot Unavailable (in_use == 2)
                      ▼                                               ▼
             [Acquire Slot (in_use + 1)]                     [Re-enqueue to SQS]
                      │                                      DelaySeconds = 30
                      ▼                                      requeue_count = requeue_count + 1
             [Update Job: PROVISIONING]                               │
                      │                                               ▼
                      ▼                                      [Acknowledge Original]
             [EC2: RunInstances API]
             (Launch Template + Rendered User-Data)
```

1. **Queue Polling:** The `job_launcher` Lambda is triggered by SQS (batch size = 1, maximum concurrency = 2).
2. **Atomic Capacity Check:** To prevent cloud bill shocks, CloudTrain enforces a strict cluster cap of `MAX_CONCURRENT_INSTANCES` (default 2). In DynamoDB, a special item `job_id="__capacity__"` maintains the current `in_use` count.
3. **Back-Pressure Handling:**
   - If `in_use >= 2`, no compute slot is available. The launcher **re-enqueues** a copy of the message back into SQS with `DelaySeconds=30` and increments `requeue_count`, then acknowledges the original message. This prevents SQS receive counts from exhausting and avoids premature Dead-Letter Queueing.
   - If `requeue_count >= 120` (~1 hour of waiting), the job is marked `FAILED` with code `CAPACITY_TIMEOUT`.
4. **Slot Acquisition:** If `in_use < 2`, DynamoDB executes a conditional update (`ADD in_use :1 WHERE in_use < :max`). If successful, the job status moves from `QUEUED` ➔ `PROVISIONING`.
5. **EC2 Provisioning:** The launcher invokes `ec2:RunInstances` using an AWS Launch Template. It injects a dynamically rendered bash **User-Data** script with strictly sanitized environment variables (job ID, S3 bucket, status queue URL). An EC2 idempotency token (`ClientToken=job_id`) guarantees duplicate instances can never be created.

---

### Flow D: Training Execution & Real-Time Telemetry
```
[EC2 Host Boot] ──> [dnf install docker] ──> [docker login ECR & pull image]
                                                        │
                                                        ▼
                                             [docker run cloudtrain-trainer]
                                                        │
                      ┌─────────────────────────────────┴─────────────────────────────────┐
                      ▼                                                                   ▼
             [ML Training Pipeline]                                            [Live Status Reporter]
         1. BOOTSTRAP (5%)                                                     Monotonic seq (1, 2, 3...)
         2. DOWNLOADING (10%)                                                              │
         3. VALIDATING (15%)                                                               ▼
         4. PREPROCESSING (25%)                                                    [SQS Status Queue]
         5. TRAINING (40-75%)                                                              │
         6. EVALUATING (80%)                                                               ▼
         7. EXPLAINING (88%)                                                     [status_updater Lambda]
         8. UPLOADING (95%)                                                                │
         9. DONE (100%)                                                                    ▼
                                                                                   [DynamoDB Jobs Table]
                                                                                   Conditional: seq > last_seq
```

1. **Host Bootstrap:** The EC2 instance boots Amazon Linux 2023. The user-data script installs and starts Docker, logs into ECR using instance IAM credentials, and pulls the `cloudtrain-trainer` image.
2. **Isolated Container Launch:** The host runs the container:
   `docker run --rm -e JOB_ID -e USER_ID -e DATA_BUCKET -e STATUS_QUEUE_URL cloudtrain-trainer`
3. **Telemetry Streaming:** The container's Python process initializes a `StatusReporter`. At every pipeline stage, it pushes a structured JSON event to the `cloudtrain-status` SQS queue with an incremental sequence number (`seq = 1, 2, 3...`), stage name, and progress percentage.
4. **Sequence & Rank-Guarded Updates:** The `status_updater` Lambda consumes the status queue and applies updates to DynamoDB using conditional expressions:
   `ConditionExpression: (attribute_not_exists(last_seq) OR last_seq < :seq) AND NOT status IN (terminal)`
   **Why this matters:** SQS standard queues do not guarantee message order. If event 4 arrives before event 3, event 3 will be safely dropped by DynamoDB, preventing progress bars from jumping backward.
5. **Frontend Polling & Logs:** The React frontend polls `GET /jobs/{id}` every 5 seconds to render the progress stepper, and calls `GET /jobs/{id}/logs` to display live console output.

---

### Flow E: Artifact Generation & Instance Self-Termination
```
[Trainer Container]
  │
  ├── 1. Writes artifacts: model.joblib, metrics.json, feature_importance.json,
  │      preprocessing_report.json, model_card.md, predict_example.py, logs.txt
  ├── 2. Uploads all files to S3 prefix: jobs/{user_id}/{job_id}/artifacts/
  ├── 3. Sends SUCCEEDED status event to SQS Status Queue
  └── 4. Container process exits (code 0)
          │
          ▼
[EC2 Host User-Data]
  │
  └── trap 'shutdown -h now' EXIT triggers
          │
          ▼
[AWS EC2 Infrastructure]
  │
  └── instance_initiated_shutdown_behavior = "terminate"
      ==> EC2 instance instantly terminates and deletes its own EBS volume!
          │
          ▼
[status_updater Lambda]
  │
  └── Receives SUCCEEDED event
      ├── Sets status: SUCCEEDED, finished_at: now
      └── Releases capacity slot in DynamoDB (__capacity__.in_use - 1)
```

1. **Artifact Generation:** On completion of training and evaluation, the container serializes the trained model pipeline into `model.joblib`. It writes evaluation metrics (`metrics.json`), feature importances, preprocessing decisions, an auto-generated `model_card.md`, a standalone offline prediction script (`predict_example.py`), and pinned dependencies (`requirements.txt`).
2. **S3 Upload:** All artifacts and complete execution logs (`logs.txt`) are uploaded to S3 under `jobs/{user_id}/{job_id}/artifacts/`.
3. **Terminal Notification:** The container pushes a `SUCCEEDED` status event to SQS.
4. **Self-Termination:** When the training container exits, the host user-data shell script hits its `trap 'shutdown -h now' EXIT` handler. Because the EC2 instance was launched with `instance_initiated_shutdown_behavior="terminate"`, the OS shutdown causes AWS to **immediately terminate the VM** and delete its root EBS disk. No zombie instances can survive!
5. **Capacity Slot Release:** The `status_updater` Lambda processes the terminal event and atomically decrements `__capacity__.in_use` in DynamoDB, freeing the slot for the next queued job.

---

## 4. Comprehensive AWS Services Breakdown

During your viva presentation, you should be able to explain **why each service was chosen**, **what role it plays**, and **how it aligns with cloud cost optimization**:

| AWS Service | Category | Specific Role in CloudTrain | Why Chosen over Alternatives | Cost / Free Tier Consideration |
| :--- | :--- | :--- | :--- | :--- |
| **Amazon S3** | PaaS (Storage) | Stores raw uploaded CSVs, job configurations, training logs, and serialized model artifacts (`model.joblib`). | **Industry standard object store.** 99.999999999% durability. Supports Presigned URLs, allowing clients to upload/download directly without overloading API compute. | First 5 GB free. Lifecycle policies automatically delete artifacts after 30 days and logs after 14 days to prevent storage accumulation. |
| **Amazon DynamoDB** | PaaS (NoSQL Database) | Metadata storage for datasets, job states, timestamps, evaluation summaries, and atomic capacity counters. | **Sub-millisecond latency & zero idle cost.** On-Demand pay-per-request mode costs $0 when idle. Offers native atomic counters (`ADD in_use :1`) and conditional writes. Chosen over RDS because RDS has no permanent free tier and incurs continuous 24/7 hourly charges. | 25 GB free storage and 25 WCU/RCU in AWS Free Tier. $0.00 idle cost. |
| **Amazon SQS** | PaaS (Messaging) | Asynchronous messaging queue. Decouples API from EC2 launcher (`jobs-queue`) and decouples container from database updater (`status-queue`). | **Fault tolerance & microservices decoupling.** Standard queues absorb burst traffic and provide back-pressure. Built-in Dead Letter Queues (DLQ) isolate poison messages. | 1,000,000 free requests per month. Completely free at student scale. |
| **AWS Lambda** | FaaS (Serverless Compute) | Executes application logic: `api` (REST routing), `dataset_profiler` (CSV parsing), `job_launcher` (EC2 dispatch), `status_updater` (state sync), `watchdog` (heartbeat), `dlq_reaper` (dead letter recovery). | **Event-driven elasticity.** Scales instantly from zero to thousands of executions, billing only for exact execution milliseconds. Runs outside VPC to eliminate expensive NAT Gateway costs. | 1,000,000 free requests and 3.2 million seconds of compute time per month. |
| **Amazon EC2** | IaaS (Compute) | Heavy-duty compute environment executing the scikit-learn/xgboost training algorithms inside Docker. | **Full hardware allocation.** Lambda is limited to 15 minutes, 10 GB disk, and restricted vCPUs. EC2 provides unconstrained CPU/RAM for arbitrary training workloads. Configured with self-termination to act like serverless compute. | Uses burstable `t3.small` / `t3.medium`. Only billed for the minutes a job is actively running (typically 2-4 minutes = less than $0.01 per run). |
| **Amazon API Gateway** | PaaS (Networking) | Exposes REST endpoints to the internet, terminates HTTPS, routes requests to Lambda, and validates Cognito JWTs. | **HTTP API v2 was chosen** over classic REST API. It is 70% cheaper, provides lower latency, and has built-in native OIDC/JWT authorizer without requiring custom authorizer Lambdas. | 1,000,000 free API calls per month for 12 months. |
| **Amazon Cognito** | PaaS (Security/Identity) | User authentication, user pool management, password hashing, email verification, and issuance of cryptographically signed JWT access tokens. | **Secure identity without backend management.** Offloads credential storage, password recovery, and SRP (Secure Remote Password) protocol from custom backend code. | 50,000 Monthly Active Users (MAUs) completely free forever. |
| **Amazon CloudFront** | PaaS (Content Delivery) | Global CDN serving the React Single Page Application (SPA) static files from S3 with low latency and TLS encryption. | **High performance & secure delivery.** Protects S3 web bucket via Origin Access Control (OAC), so the S3 bucket stays 100% private. | 1 TB data transfer out per month free. |
| **Amazon ECR** | PaaS (Registry) | Private Docker container registry hosting the `cloudtrain-trainer` Docker image. | Seamless IAM-authenticated image pulling from EC2 instances using the instance profile role. | 500 MB private storage free per month. |
| **Amazon EventBridge** | PaaS (Scheduler) | Serverless cron trigger that invokes the `watchdog` Lambda every 5 minutes. | Eliminates the need to run an always-on background server or cron daemon just to check system health. | Free tier covers all EventBridge scheduled rule invocations. |
| **Amazon CloudWatch** | PaaS (Observability) | Centralized logging (`/cloudtrain/prod/training`), metric filters, queue depth alarms, and cost budget monitoring. | Captures container and Lambda logs; metric filters detect error spikes; triggers SNS email notifications on DLQ arrivals. | 5 GB log ingestion and 10 custom alarms free. |
| **AWS IAM** | Security / Governance | Enforces Least Privilege access. Distinct IAM roles for API Gateway, each Lambda function, and EC2 trainer instance. | Eliminates static access keys. EC2 instances and Lambdas assume temporary credentials dynamically via instance profiles and execution roles. | 100% Free AWS governance service. |
| **Terraform (IaC)** | Tooling / Orchestration | Automates 100% of cloud resource provisioning and destruction across all 10 architectural modules. | Guarantees complete infrastructure reproducibility. Any teammate or professor can deploy or tear down the entire platform with one command. | Open-source declarative tool. |

---

## 5. Docker Containerization (Basic & Essential Role)

> *Professor note: Docker is kept straightforward and focused purely on application isolation, without unnecessary kernel complexity.*

### Why Docker is Used in CloudTrain
In machine learning projects, a common failure point is the **"It worked on my machine"** dilemma: differing versions of Python, NumPy, SciPy, or C-libraries (like `libgomp` for OpenMP) lead to runtime crashes when code moves to the cloud.

CloudTrain uses Docker for **three fundamental reasons**:
1. **Dependency Encapsulation:** The training code requires an exact scientific stack (`python:3.11-slim`, `scikit-learn==1.5.*`, `xgboost==2.1.*`, `pandas==2.2.*`, `numpy<2.1`). Docker packages these libraries into a single immutable container image (`cloudtrain-trainer`).
2. **Environment Parity:** The exact same Docker image runs on an EC2 instance in AWS and on a student's local laptop during offline testing. Zero code modification is needed between local and cloud runs.
3. **Security Sandboxing:** The container runs as an unprivileged non-root user (`trainer`, UID 1000). Even if a malicious dataset attempted an exploit, the process cannot modify the underlying host operating system.

### Container Lifecycle
The container is purely **ephemeral (stateless)**:
- It receives configuration and credentials strictly via environment variables (`JOB_ID`, `DATA_BUCKET`, `STATUS_QUEUE_URL`).
- It starts up ➔ downloads dataset ➔ trains model ➔ pushes status events to SQS ➔ uploads model artifacts to S3 ➔ exits immediately with status code `0` (or `1` on error).
- The `--rm` Docker flag ensures the container is deleted immediately upon exit.

---

## 6. Critical Technicalities & Distributed Systems Concepts

This section contains the advanced distributed systems concepts that professors love to probe during viva presentations:

### 1. Monotonic State Machine & State Rank Enforcement
In distributed systems, asynchronous message queues (like SQS Standard) guarantee **at-least-once delivery**, which means messages can arrive **out of order or duplicated**.

If a naive database update were used, a delayed `RUNNING` event could overwrite a subsequent `SUCCEEDED` event, corrupting the database state! CloudTrain solves this mathematically using **Monotonic State Ranking**:

$$\text{QUEUED (1)} < \text{PROVISIONING (2)} < \text{RUNNING (3)} < \text{UPLOADING (4)} < \text{TERMINAL (5)}$$

*Terminal states:* `SUCCEEDED`, `FAILED`, `CANCELLED`, `TIMED_OUT`.

**The Implementation Rule:**
- State transitions are strictly monotonic (rank can only increase).
- Once a job reaches rank 5 (terminal), it can **never** be updated again.
- In `backend/common/states.py`, this is validated in Python, and enforced in DynamoDB via atomic condition expressions:
```python
cond_expr = (
    "attribute_exists(job_id) "
    "AND (attribute_not_exists(last_seq) OR last_seq < :seq) "
    "AND NOT #st IN (:succ, :fail, :canc, :tout)"
)
```
If an out-of-order or duplicate message arrives, the conditional check fails and DynamoDB silently ignores the stale update.

---

### 2. Distributed Concurrency & Atomic Capacity Slots
To prevent a single user or runaway script from launching 50 EC2 instances and bankrupting the student AWS account, CloudTrain implements a **Distributed Semaphore (Capacity Slot)** in DynamoDB:

- DynamoDB stores a special record: `Key: {"job_id": "__capacity__"}, Attribute: {"in_use": 0}`.
- **Acquiring a Slot:** Before calling `ec2:RunInstances`, the `job_launcher` executes an atomic conditional update:
  `ADD in_use :1 WHERE in_use < :max_concurrent` (where `:max_concurrent = 2`).
  If two jobs attempt this simultaneously, DynamoDB's optimistic concurrency guarantees that only one succeeds; the second receives a `ConditionalCheckFailedException`.
- **Releasing a Slot:** When a job finishes (`SUCCEEDED`, `FAILED`, or `CANCELLED`), the `status_updater` releases the slot using a DynamoDB transaction (`TransactWriteItems`), decrementing `in_use - 1` and recording `slot_released = true` on the job item to ensure it is released exactly once.

---

### 3. Asynchronous Decoupling & At-Least-Once Toleration
Why did we use **Amazon SQS Standard** instead of SQS FIFO?
- **Cost & Quota:** SQS standard has an almost unlimited throughput, is supported in all AWS regions, and falls within the permanent free tier (1,000,000 requests/month).
- **Simplicity:** FIFO queues require message group IDs, deduplication IDs, and have stricter throughput limits.
- **Application-Layer Idempotency:** Instead of paying for FIFO infrastructure, CloudTrain handles deduplication in software:
  1. Every status event published by the trainer contains a strictly increasing integer sequence number: `seq = 1, 2, 3...`.
  2. DynamoDB stores `last_seq`. If an event arrives with `seq <= last_seq`, it is rejected as a duplicate.

---

### 4. Dead-Letter Queues (DLQ) & Failure Recovery
In any queue-based architecture, a **"Poison Pill"** (a malformed message that crashes the consumer) can cause an infinite loop: message is read ➔ consumer crashes ➔ visibility timeout expires ➔ message reappears ➔ consumer crashes again.

CloudTrain implements multi-stage DLQ protection:
1. **Redrive Policy:** The `jobs` queue has `maxReceiveCount = 3`. If `job_launcher` fails to process a job 3 times, SQS moves it to `cloudtrain-jobs-dlq`.
2. **Automated DLQ Reaper:** The `dlq_reaper` Lambda monitors the DLQ. When a message lands there:
   - It parses the `job_id`.
   - Transitions the job in DynamoDB to `FAILED` with error code `DISPATCH_FAILED`.
   - Releases any reserved capacity slots.
   - Deletes the poison message from the DLQ so the system returns to healthy operation.
3. **CloudWatch Alarm:** An alarm triggers if `cloudtrain-jobs-dlq` count > 0, sending an immediate email notification via SNS.

---

### 5. The Watchdog Pattern (Heartbeat & Zombie Reaper)
What happens if an EC2 instance experiences a hardware fault, runs out of memory (OOM), or loses network connectivity mid-training without sending a failure message?

Without self-healing, the job would stay in `RUNNING` forever and the capacity slot would remain locked. CloudTrain solves this with an **EventBridge-triggered Watchdog Lambda** running every 5 minutes:
1. **Zombie Job Detection:** Queries all jobs currently in `PROVISIONING` or `RUNNING`. If `now - last_event_at > 15 minutes` during provisioning, or `> MAX_RUNTIME_MINUTES (60 min)`, the watchdog marks the job `TIMED_OUT` and releases the slot.
2. **Dead Instance Verification:** Calls `ec2:DescribeInstances`. If AWS reports the EC2 instance is `terminated` or `shutting-down` while the job in DynamoDB is still non-terminal, the watchdog sets status to `FAILED` with error `INSTANCE_LOST`.
3. **Orphan Instance Termination:** Scans EC2 for any instance tagged `Role=trainer` that is older than 90 minutes and terminates it forcefully.
4. **Capacity Reconciliation:** Re-counts all active jobs and resets `__capacity__.in_use` if database counter drift has occurred.

---

### 6. Multi-Tenant Security & Zero-Trust Isolation
- **No Inbound Ports (Zero Ingress):** The EC2 trainer security group has **zero inbound rules** (`ingress = []`). No SSH (port 22) is open. Admin access, if ever needed for debugging, is performed via AWS Systems Manager (SSM) Session Manager through an encrypted outbound tunnel.
- **Data Isolation:** S3 storage and DynamoDB tables partition records strictly by `user_id` (derived from Cognito JWT claims). The API enforces that User A can never query, download, or delete User B's datasets or models; any mismatched ID returns an immediate `404 Not Found` (preventing resource enumeration).
- **Pre-signed Scoping:** Pre-signed URLs for S3 upload and download expire in 15 minutes and restrict HTTP verbs, file sizes, and exact S3 keys.
- **IMDSv2 Protection:** EC2 launch templates enforce Instance Metadata Service Version 2 (IMDSv2) with `http_put_response_hop_limit = 2`, preventing SSRF (Server-Side Request Forgery) attacks while allowing Docker bridge containers to fetch temporary IAM credentials.

---

### 7. FinOps & Cost-Guardrail Engineering
The most impressive aspect of CloudTrain for an engineering professor is its **FinOps (Financial Operations) design**:

| Anti-Pattern to Avoid | What CloudTrain Does Instead | Monthly Cost Saved |
| :--- | :--- | :--- |
| **Running RDS Postgres 24/7** | Uses DynamoDB On-Demand (serverless pay-per-request) | ~$18 - $25 / month |
| **Using AWS NAT Gateway** | Lambdas run outside VPC; EC2 instances use public subnets + S3 Gateway Endpoint | ~$32 / month |
| **Application Load Balancers (ALB)** | Uses API Gateway HTTP API v2 (serverless) | ~$16 - $20 / month |
| **Always-On EC2 Training Server** | Ephemeral EC2 instances that self-terminate on completion (`shutdown -h now`) | ~$15 - $30 / month |
| **AWS SageMaker Canvas Base Instance** | Custom containerized trainer image running on standard EC2 instances | ~$50+ / month |
| **Total Baseline Idle Cost** | **$0.00 / month (100% Free Tier Covered)** | **~$120+ / month saved** |

---

## 7. Local Emulation vs. AWS Cloud Execution

CloudTrain features a dual execution engine, allowing full offline testing without cloud credentials:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Local Development Mode                          │
│                                                                        │
│   • Moto Server (:4566) emulates S3, DynamoDB, and SQS in-memory       │
│   • backend/local_server.py translates HTTP to API Gateway v2 payloads │
│   • job_launcher spawns local Python processes or local Docker tasks   │
│   • LOCAL_AUTH_BYPASS=1 bypasses Cognito for rapid UI testing          │
│   • Total AWS Cost: Exactly $0.00                                      │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   │ Identical interfaces & data contracts
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       AWS Production Cloud Mode                        │
│                                                                        │
│   • Real AWS S3, DynamoDB On-Demand, SQS Standard + DLQ                │
│   • Real API Gateway HTTP API + Amazon Cognito JWT Authorizer          │
│   • Real on-demand EC2 t3.small instances running Docker from ECR      │
│   • 100% deployed via Terraform & GitHub Actions OIDC CI/CD            │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Professor Viva & Presentation Q&A Preparation

Here are the top 10 questions a cloud computing professor is most likely to ask, along with clear, technical, bulletproof answers:

#### Q1: "Why did you use Amazon SQS and Lambda instead of AWS Step Functions for orchestration?"
> **Answer:** "Step Functions is excellent for complex state graphs with human approvals or branching microservices. However, CloudTrain's lifecycle is strictly linear: Queued ➔ Provisioning ➔ Running ➔ Uploading ➔ Succeeded. Implementing this with SQS standard queues and an event-driven `status_updater` Lambda is lighter, has lower latency, costs significantly less (SQS has 1M free requests/month), and allowed us to implement custom distributed systems patterns like monotonic state ranking and atomic capacity counters in DynamoDB."

#### Q2: "Why did you choose DynamoDB instead of a traditional relational database like PostgreSQL or AWS RDS?"
> **Answer:** "Two reasons: cost and architectural suitability. First, RDS instances must run 24/7, incurring a baseline cost of $18–$25/month with no permanent free tier. DynamoDB in on-demand mode has zero idle cost ($0.00 when no jobs run). Second, DynamoDB provides sub-millisecond key-value lookups and native atomic operations (`ADD in_use :one`), which allowed us to build an atomic distributed concurrency lock without needing an external caching layer like Redis."

#### Q3: "What prevents an EC2 instance from continuing to run if the training script crashes or freezes?"
> **Answer:** "We have three distinct layers of defense:
> 1. **OS Trap:** The user-data script wraps execution in a bash trap (`trap 'shutdown -h now' EXIT`). Whether the container succeeds or crashes with an unhandled exception, the host OS executes shutdown. With `instance_initiated_shutdown_behavior="terminate"`, AWS deletes the instance immediately.
> 2. **Python Watchdog Alarm:** The trainer's `main.py` starts a background timer that forcibly raises a `TrainingTimeout` exception if execution exceeds `MAX_RUNTIME_SECONDS`.
> 3. **Platform Watchdog Lambda:** Every 5 minutes, an independent Lambda inspects running instances. If an instance has stopped reporting progress for >15 minutes, or has run past the 60-minute ceiling, the watchdog explicitly calls `ec2:TerminateInstances`."

#### Q4: "How does the system handle SQS message duplication and out-of-order delivery?"
> **Answer:** "SQS Standard queues provide at-least-once delivery, meaning duplicates and re-ordered messages are expected. We solved this at the database layer using **monotonic sequence numbers (`seq`) and state ranking**. Every event emitted by the container has an incremental sequence counter (`seq=1, 2, 3...`). DynamoDB applies updates using a condition expression: `ConditionExpression: last_seq < :seq`. If a duplicate or out-of-order event arrives, DynamoDB fails the condition check and safely drops the update without corrupting the progress bar."

#### Q5: "Why do users upload datasets directly to S3 instead of sending them to the API Gateway?"
> **Answer:** "API Gateway has a hard payload limit of 10 MB, and passing large files through Lambda consumes significant RAM and compute time, which drives up costs. By having the API generate an **S3 Pre-Signed POST URL**, the browser streams the CSV directly to S3. This supports files up to 100 MB, provides upload progress bars to the user, and triggers an event-driven `dataset_profiler` Lambda only after the file has safely landed in object storage."

#### Q6: "Why are your Lambda functions not placed inside a VPC?"
> **Answer:** "If a Lambda function is placed inside a VPC, it cannot access public AWS service APIs (DynamoDB, SQS, S3) unless you provision either a **NAT Gateway** (which costs ~$32/month continuously) or private **VPC Interface Endpoints** (PrivateLink, which costs ~$7/month per AZ per service). Since our Lambdas only interact with AWS managed services over HTTPS and do not connect to private databases, running them outside a VPC is an intentional architectural decision that saved over $40/month while maintaining full security via IAM."

#### Q7: "How is multi-tenancy and data security enforced?"
> **Answer:** "All API routes sit behind API Gateway with a Cognito JWT Authorizer. When a request arrives, API Gateway cryptographically verifies the JWT signature and extracts the user's `sub` claim (UUID). Every subsequent database query and S3 key prefix is scoped by `user_id`. Furthermore, all read and delete operations verify ownership; if User A attempts to access User B's job ID, the API returns a `404 Not Found` (rather than a 403) to prevent resource existence enumeration."

#### Q8: "What happens if 10 users submit training jobs simultaneously?"
> **Answer:** "The API responds to all 10 users within 2 seconds with `HTTP 202 Accepted` and puts 10 messages into the `jobs-queue`. The `job_launcher` Lambda processes messages up to our configured capacity limit of `MAX_CONCURRENT_INSTANCES=2`. The first two jobs acquire slots in DynamoDB and launch EC2 instances. The remaining 8 jobs find that `in_use == 2`; the launcher re-enqueues them into SQS with a 30-second delay. As each running job finishes, it decrements the counter, and the queued jobs automatically pick up the freed slots. The platform gracefully buffers load without crashing or exceeding cost limits."

#### Q9: "Why did you use Docker on EC2 instead of running Python directly on the VM host?"
> **Answer:** "Running via Docker provides immutability and hermetic isolation. It ensures the scientific Python stack (Scikit-learn, XGBoost, Pandas) is identical across developer laptops and cloud instances. Additionally, it runs under a non-root user account, and allows the platform to upgrade or change ML libraries simply by building and pushing a new image tag to ECR without needing to recreate or re-bake custom EC2 AMIs."

#### Q10: "If you had more time or budget, what would be the next architectural evolution of CloudTrain?"
> **Answer:** "Three key enhancements:
> 1. **Spot Instance Integration:** Using EC2 Spot Instances with automated on-demand fallback would reduce compute costs by another 70%.
> 2. **WebSocket or Server-Sent Events (SSE):** Replacing client HTTP polling with AWS API Gateway WebSocket APIs or AWS AppSync for instant event streaming.
> 3. **Model Serving & Inference Endpoints:** Adding an automated deployment button that packages the `model.joblib` into a serverless AWS Lambda inference endpoint behind API Gateway."

---

## 9. Quick Verification & Demonstration Commands

When presenting the project to your professor, use these quick commands to demonstrate correctness and test coverage:

```bash
# 1. Run all backend unit tests (covers state machine, schemas, capacity slots)
pytest backend/tests

# 2. Run trainer pipeline tests (covers preprocessing, classification, regression)
pytest trainer/tests

# 3. Verify Terraform infrastructure definition
cd infra
terraform validate

# 4. Run local end-to-end stack for live demonstration
# Terminal 1:
python backend/local_server.py

# Terminal 2:
cd frontend && npm run dev
# Open http://localhost:5173
```
