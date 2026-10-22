# CloudTrain Architecture

For the complete, professor-ready architectural dossier, request flows, AWS service breakdowns, and viva defense guide, see the comprehensive master document:
👉 **[MASTER_PROJECT_GUIDE.md](./MASTER_PROJECT_GUIDE.md)**

---

## High-Level Architecture Overview

CloudTrain is a zero-cost cloud and local automated machine learning (AutoML) platform. It provides a no-code visual interface for uploading datasets, training tabular machine learning models (Classification & Regression), and downloading serialized model bundles with full evaluation metrics.

```mermaid
flowchart TD
    subgraph Client ["Client Layer"]
        SPA["React 18 + TS Frontend (Vite)"]
    end

    subgraph Identity ["Identity & Ingress"]
        COG["Amazon Cognito (User Pool)"]
        CF["Amazon CloudFront (CDN)"]
        APIGW["API Gateway v2 (HTTP API + JWT Authorizer)"]
    end

    subgraph Serverless ["Serverless Microservices (AWS Lambda)"]
        API_LAMBDA["api Lambda (REST Router)"]
        PROF_LAMBDA["dataset_profiler Lambda"]
        LAUNCH_LAMBDA["job_launcher Lambda"]
        STATUS_LAMBDA["status_updater Lambda"]
        REAP_LAMBDA["dlq_reaper Lambda"]
        DOG_LAMBDA["watchdog Lambda (EventBridge 5m)"]
    end

    subgraph Storage ["Managed Storage & State"]
        S3_DATA[("Amazon S3 (Data & Artifacts)")]
        DDB_JOBS[("DynamoDB (Jobs & Capacity)")]
        DDB_DATA[("DynamoDB (Datasets)")]
        ECR[("Amazon ECR (Docker Images)")]
    end

    subgraph Messaging ["Message Queues (Amazon SQS)"]
        Q_JOBS[["Jobs Queue + DLQ"]]
        Q_STATUS[["Status Queue + DLQ"]]
    end

    subgraph Compute ["On-Demand Compute (IaaS)"]
        EC2["EC2 On-Demand Instance (t3.small/medium)"]
        CONTAINER["cloudtrain-trainer (Docker Container)"]
    end

    SPA -->|1. Direct Presigned Upload| S3_DATA
    SPA -->|2. Authenticate| COG
    SPA -->|3. REST Requests (JWT)| APIGW
    APIGW --> API_LAMBDA
    API_LAMBDA --> DDB_JOBS
    API_LAMBDA --> DDB_DATA
    API_LAMBDA -->|Enqueue Job| Q_JOBS

    S3_DATA -->|ObjectCreated Event| PROF_LAMBDA
    PROF_LAMBDA --> DDB_DATA

    Q_JOBS --> LAUNCH_LAMBDA
    LAUNCH_LAMBDA -->|Atomic Slot Check| DDB_JOBS
    LAUNCH_LAMBDA -->|RunInstances (Launch Template)| EC2

    EC2 --> CONTAINER
    ECR -->|Pull Image| CONTAINER
    S3_DATA -->|Download CSV & Config| CONTAINER
    CONTAINER -->|Stream Status Events| Q_STATUS
    CONTAINER -->|Upload Model & Metrics| S3_DATA

    Q_STATUS --> STATUS_LAMBDA
    STATUS_LAMBDA -->|Sequence-Guarded Update & Release Slot| DDB_JOBS

    DOG_LAMBDA -->|Reap Zombies & Drift Check| EC2
    DOG_LAMBDA --> DDB_JOBS
```

---

## Core Principles
1. **Decoupled Asynchrony:** No HTTP request ever blocks on long-running ML training or compute provisioning.
2. **Strict FinOps / Zero Idle Cost:** No 24/7 relational databases or NAT Gateways. Compute is 100% ephemeral and self-terminating.
3. **Monotonic Progression:** Database state updates enforce monotonic sequence numbers and state rank guarantees.
4. **Dual Engine Execution:** Runs identically on AWS (Production) or local Moto emulation (zero-cost offline testing).
