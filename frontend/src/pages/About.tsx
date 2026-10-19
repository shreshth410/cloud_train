import React from "react";
import {
  Cloud,
  Cpu,
  Lock,
  Layers,
  ShieldCheck,
  Zap,
} from "lucide-react";

export const About: React.FC = () => {
  return (
    <div className="space-y-10 max-w-5xl mx-auto">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-cyan-950 text-cyan-300 border border-cyan-800/80">
            Platform Architecture
          </span>
        </div>
        <h1 className="text-3xl font-extrabold tracking-tight text-white">
          CloudTrain — Zero-Cost ML Architecture
        </h1>
        <p className="text-sm text-slate-400 max-w-3xl leading-relaxed">
          CloudTrain delivers a no-code, serverless machine learning platform on AWS at zero operational cost. Built from scratch with infrastructure-as-code, decoupled asynchronous queueing, and strictly self-terminating compute instances.
        </p>
      </div>

      {/* Visual System Architecture Diagram */}
      <div className="p-6 rounded-2xl glass-panel space-y-4">
        <h2 className="text-lg font-bold text-white flex items-center gap-2">
          <Layers className="w-5 h-5 text-indigo-400" />
          End-to-End System Topology
        </h2>

        <div className="p-6 rounded-xl bg-[#050811] border border-slate-800 text-xs text-slate-300 space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Frontend & Edge */}
            <div className="p-4 rounded-lg bg-slate-900/80 border border-slate-800 space-y-2">
              <div className="flex items-center gap-2 text-cyan-400 font-semibold">
                <Cloud className="w-4 h-4" />
                Frontend & Edge
              </div>
              <p className="text-slate-400 text-[11px]">
                CloudFront CDN + S3 SPA + Cognito User Pool (SRP authentication).
              </p>
            </div>

            {/* Serverless Control Plane */}
            <div className="p-4 rounded-lg bg-slate-900/80 border border-slate-800 space-y-2">
              <div className="flex items-center gap-2 text-indigo-400 font-semibold">
                <Zap className="w-4 h-4" />
                Control Plane (Serverless)
              </div>
              <p className="text-slate-400 text-[11px]">
                API Gateway HTTP API + 7 Python Lambdas + SQS FIFO/Standard queues + DynamoDB on-demand tables.
              </p>
            </div>

            {/* Elastic Training Workers */}
            <div className="p-4 rounded-lg bg-slate-900/80 border border-slate-800 space-y-2">
              <div className="flex items-center gap-2 text-emerald-400 font-semibold">
                <Cpu className="w-4 h-4" />
                Data & Compute Plane
              </div>
              <p className="text-slate-400 text-[11px]">
                S3 Data Bucket + ECR Container Registry + Self-terminating EC2 Launch Templates.
              </p>
            </div>
          </div>

          {/* ASCII / Box Architecture Flow */}
          <div className="p-4 rounded-lg bg-slate-950 font-mono text-[11px] leading-relaxed text-slate-300 overflow-x-auto border border-slate-800/80">
            <pre>{`[User Browser]
   │
   ├─► S3 Web Bucket (via CloudFront OAC) ──────────────► React SPA
   ├─► Cognito User Pool (SRP Auth) ────────────────────► JWT Token
   ├─► API Gateway HTTP API (JWT Authorizer)
   │     │
   │     ├─► Lambda: api (CRUD jobs/datasets/quotas) ───► DynamoDB
   │     ├─► Direct-to-S3 Pre-signed Upload ────────────► S3 Data Bucket
   │
[S3 Data Bucket]
   └─► S3 ObjectCreated Event ──► Lambda: dataset_profiler ──► DynamoDB (READY)
   │
[Jobs Queue (SQS)]
   ▲ Enqueued by api
   │
   └─► Lambda: job_launcher (Capacity Lock & Launch)
         │
         └─► EC2 On-Demand Instance (t3.small / t4g.small)
               │
               ├─► Pulls Docker Image from ECR
               ├─► Downloads Dataset & Config from S3
               ├─► Trains Model (Scikit-Learn / XGBoost)
               ├─► Emits Status Progress (seq, stage) ──► SQS Status Queue
               │                                                │
               │                                                ▼
               │                                      Lambda: status_updater ──► DynamoDB
               ├─► Uploads model.joblib, metrics.json ──► S3 Data Bucket
               │
               └─► TERMINATES SELF (Trap / Shutdown / Watchdog Sweeper)`}</pre>
          </div>
        </div>
      </div>

      {/* Core Design Principles & Cost Guardrails */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="p-6 rounded-2xl glass-panel space-y-3">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            Section 17 Cost Guardrails
          </h3>
          <ul className="text-xs text-slate-300 space-y-2 list-disc list-inside">
            <li>
              <strong>Zero NAT Gateways & ALBs:</strong> Saves ~$32/month by running compute in public subnets with direct Internet Gateway routing.
            </li>
            <li>
              <strong>Self-Terminating Compute:</strong> EC2 instances shut down with termination policy immediately upon pipeline finish.
            </li>
            <li>
              <strong>Concurrency Cap:</strong> Hardware capacity is strictly limited to 2 simultaneous workers via DynamoDB atomic permits.
            </li>
            <li>
              <strong>Watchdog Reconciliation:</strong> Background timer sweeps orphan instances and reclaims stuck capacity slots.
            </li>
          </ul>
        </div>

        <div className="p-6 rounded-2xl glass-panel space-y-3">
          <h3 className="text-base font-bold text-white flex items-center gap-2">
            <Lock className="w-5 h-5 text-cyan-400" />
            Security & Compliance
          </h3>
          <ul className="text-xs text-slate-300 space-y-2 list-disc list-inside">
            <li>
              <strong>Pre-signed S3 URLs:</strong> Client never holds AWS credentials; data bucket enforces SSE and TLS 1.2+.
            </li>
            <li>
              <strong>Strict Multi-Tenant Isolation:</strong> Every DynamoDB query and S3 path is scoped to Cognito user identity.
            </li>
            <li>
              <strong>IMDSv2 Enforced:</strong> All worker instances require session tokens for metadata security.
            </li>
            <li>
              <strong>PreSignUp Allow-List:</strong> Unauthorized external email domains cannot create resources or incur cloud charges.
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};
