import React, { useState, useEffect, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchJob,
  cancelJob,
  deleteJob,
  fetchJobResults,
  fetchJobArtifacts,
  fetchJobLogs,
} from "@/lib/api";
import { JobStatusBadge } from "@/components/StatusBadge";
import { formatDuration, formatDate } from "@/utils/formatters";
import {
  BrainCircuit,
  ArrowLeft,
  XCircle,
  Trash2,
  Copy,
  Download,
  AlertTriangle,
  Terminal,
  Activity,
  BarChart3,
  ShieldAlert,
  RotateCcw,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ScatterChart,
  Scatter,
  CartesianGrid,
} from "recharts";

const STAGES = [
  { id: "QUEUED", label: "Queued", desc: "Waiting in SQS queue" },
  { id: "PROVISIONING", label: "Provisioning", desc: "Booting EC2 worker" },
  { id: "PREPROCESSING", label: "Preprocessing", desc: "Encoding & imputing" },
  { id: "TRAINING", label: "Training", desc: "Fitting model & CV" },
  { id: "EVALUATING", label: "Evaluating", desc: "Metrics & feature importance" },
  { id: "UPLOADING", label: "Uploading", desc: "Saving S3 artifacts" },
  { id: "SUCCEEDED", label: "Complete", desc: "Instance self-terminated" },
];

export const JobDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logEndRef = useRef<HTMLDivElement>(null);

  const [autoScroll, setAutoScroll] = useState(true);
  const [featureAggToggle, setFeatureAggToggle] = useState(false);
  const [copiedLog, setCopiedLog] = useState(false);

  // Poll job status every 3s if active, 30s once finished
  const { data: job, isLoading, error } = useQuery({
    queryKey: ["job", id],
    queryFn: () => fetchJob(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const active = ["QUEUED", "PROVISIONING", "RUNNING", "UPLOADING"].includes(
        query.state.data?.status || ""
      );
      return active ? 3000 : false;
    },
  });

  const isTerminal =
    job?.status === "SUCCEEDED" ||
    job?.status === "FAILED" ||
    job?.status === "CANCELLED" ||
    job?.status === "TIMED_OUT";

  // Fetch results when succeeded
  const { data: results } = useQuery({
    queryKey: ["job-results", id],
    queryFn: () => fetchJobResults(id!),
    enabled: !!id && job?.status === "SUCCEEDED",
  });

  // Fetch presigned artifact download URLs
  const { data: artifacts } = useQuery({
    queryKey: ["job-artifacts", id],
    queryFn: () => fetchJobArtifacts(id!),
    enabled: !!id && (job?.status === "SUCCEEDED" || job?.status === "FAILED"),
  });

  // Fetch logs with polling while running
  const { data: logData } = useQuery({
    queryKey: ["job-logs", id],
    queryFn: () => fetchJobLogs(id!),
    enabled: !!id,
    refetchInterval: isTerminal ? false : 3000,
  });

  useEffect(() => {
    if (autoScroll && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logData, autoScroll]);

  const cancelMutation = useMutation({
    mutationFn: () => cancelJob(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["job", id] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteJob(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      navigate("/jobs");
    },
  });

  const handleCloneJob = () => {
    if (!job) return;
    sessionStorage.setItem("cloudtrain_wizard_step", "7");
    sessionStorage.setItem("cloudtrain_wizard_dataset", job.dataset_id);
    sessionStorage.setItem("cloudtrain_wizard_target", job.config.target_column);
    sessionStorage.setItem("cloudtrain_wizard_task", job.config.task || "classification");
    sessionStorage.setItem(
      "cloudtrain_wizard_features",
      JSON.stringify(job.config.feature_columns || [])
    );
    sessionStorage.setItem("cloudtrain_wizard_model", job.config.model.id);
    sessionStorage.setItem(
      "cloudtrain_wizard_params",
      JSON.stringify(job.config.model.hyperparameters || {})
    );
    sessionStorage.setItem("cloudtrain_wizard_compute", job.compute_size);
    sessionStorage.setItem("cloudtrain_wizard_name", `Clone of ${job.name || job.job_id}`);
    navigate("/train");
  };

  const copyLogsToClipboard = () => {
    if (logData?.logs) {
      navigator.clipboard.writeText(logData.logs);
      setCopiedLog(true);
      setTimeout(() => setCopiedLog(false), 2000);
    }
  };

  if (isLoading) {
    return (
      <div className="p-12 text-center text-slate-400">
        <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        Loading training job details...
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="p-8 rounded-2xl glass-panel text-center space-y-4">
        <h2 className="text-lg font-semibold text-rose-400">Job Not Found</h2>
        <p className="text-xs text-slate-400">
          The requested job ID could not be located in DynamoDB.
        </p>
        <Link
          to="/jobs"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 text-slate-200 text-xs font-medium"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Jobs
        </Link>
      </div>
    );
  }

  // Determine stage progression index (0 to 6)
  const currentStageIndex = (() => {
    if (job.status === "QUEUED") return 0;
    if (job.status === "PROVISIONING") return 1;
    if (job.status === "RUNNING") {
      const s = (job.stage || "").toLowerCase();
      if (s.includes("preprocess")) return 2;
      if (s.includes("train") || s.includes("fit")) return 3;
      if (s.includes("eval") || s.includes("explain")) return 4;
      return 3;
    }
    if (job.status === "UPLOADING") return 5;
    if (job.status === "SUCCEEDED") return 6;
    return -1;
  })();

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <Link
            to="/jobs"
            className="text-xs text-slate-400 hover:text-cyan-400 flex items-center gap-1.5 transition-colors mb-2"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Jobs
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
              <BrainCircuit className="w-6 h-6 text-cyan-400" />
              {job.name || `Job ${job.job_id.slice(0, 8)}`}
            </h1>
            <JobStatusBadge status={job.status} />
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400 font-mono">
            <span>ID: {job.job_id}</span>
            <span>•</span>
            <span className="capitalize">
              {job.config?.model?.id?.replace(/_/g, " ")} ({job.compute_size})
            </span>
            <span>•</span>
            <span>Created: {formatDate(job.created_at)}</span>
            {job.duration_seconds !== undefined && (
              <>
                <span>•</span>
                <span>Duration: {formatDuration(job.duration_seconds)}</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {!isTerminal && (
            <button
              onClick={() => cancelMutation.mutate()}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-amber-950/40 border border-amber-800/60 text-amber-300 hover:bg-amber-900/60 text-xs font-medium transition-colors"
            >
              <XCircle className="w-4 h-4" />
              Cancel Job
            </button>
          )}

          <button
            onClick={handleCloneJob}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors border border-slate-700"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Clone Configuration
          </button>

          {isTerminal && (
            <button
              onClick={() => {
                if (confirm("Delete this job record permanently?")) {
                  deleteMutation.mutate();
                }
              }}
              className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-rose-400 transition-colors"
              title="Delete job"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Stage Stepper & Progress */}
      <div className="p-6 rounded-2xl glass-panel space-y-4">
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span className="font-semibold text-slate-200 uppercase tracking-wider">
            Current Stage:{" "}
            <span className="text-cyan-400 font-mono">
              {job.stage || job.status}
            </span>
          </span>
          <span className="font-mono text-cyan-300 font-medium">
            {job.progress}% Complete
          </span>
        </div>

        {/* Linear progress bar */}
        <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              job.status === "FAILED"
                ? "bg-rose-500"
                : job.status === "SUCCEEDED"
                ? "bg-emerald-500"
                : "bg-cyan-500"
            }`}
            style={{ width: `${job.progress}%` }}
          />
        </div>

        {/* Stepper timeline */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 pt-2">
          {STAGES.map((st, idx) => {
            const isPassed = currentStageIndex > idx;
            const isCurrent = currentStageIndex === idx;
            return (
              <div
                key={st.id}
                className={`p-2.5 rounded-xl border text-xs transition-colors ${
                  isCurrent
                    ? "border-cyan-500 bg-cyan-950/40 text-cyan-200 shadow-sm"
                    : isPassed
                    ? "border-emerald-900/60 bg-emerald-950/20 text-emerald-300"
                    : "border-slate-800/80 bg-slate-900/40 text-slate-500"
                }`}
              >
                <div className="font-semibold flex items-center gap-1.5">
                  <div
                    className={`w-1.5 h-1.5 rounded-full ${
                      isCurrent
                        ? "bg-cyan-400 animate-pulse"
                        : isPassed
                        ? "bg-emerald-400"
                        : "bg-slate-700"
                    }`}
                  />
                  {st.label}
                </div>
                <div className="text-[10px] text-slate-400 mt-0.5 truncate">
                  {st.desc}
                </div>
              </div>
            );
          })}
        </div>

        {job.status === "QUEUED" && (
          <div className="text-xs text-slate-400 flex items-center gap-2 pt-1">
            <Activity className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
            <span>
              Waiting for a free compute slot (Max 2 concurrent EC2 workers)...
            </span>
          </div>
        )}
      </div>

      {/* Failure Diagnostics Panel */}
      {job.status === "FAILED" && (
        <div className="p-6 rounded-2xl bg-rose-950/30 border border-rose-800/60 space-y-4">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-6 h-6 text-rose-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h3 className="text-base font-semibold text-rose-300">
                Training Execution Failed ({job.error?.code || "INTERNAL_ERROR"})
              </h3>
              <p className="text-sm text-rose-200/90">{job.error?.message}</p>
            </div>
          </div>

          <div className="flex items-center gap-4 pt-2">
            <button
              onClick={handleCloneJob}
              className="px-4 py-2 rounded-lg bg-rose-900/80 hover:bg-rose-800 text-white text-xs font-medium flex items-center gap-2 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              Clone and Adjust Settings
            </button>
            {job.error?.code === "OUT_OF_MEMORY" && (
              <span className="text-xs text-rose-300 font-medium">
                Tip: Upgrade compute tier to Medium (8 GiB RAM).
              </span>
            )}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────── */}
      {/* RESULTS & METRICS DASHBOARD (When SUCCEEDED) */}
      {/* ────────────────────────────────────────────────────────── */}
      {job.status === "SUCCEEDED" && results && (
        <div className="space-y-6">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-emerald-400" />
            Model Evaluation & Explainability
          </h2>

          {/* Headline Metric Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {results.task === "classification" ? (
              <>
                <div className="p-4 rounded-xl glass-card">
                  <span className="text-xs text-slate-400 uppercase">Accuracy</span>
                  <div className="text-2xl font-bold text-emerald-400 mt-1 font-mono">
                    {((results.metrics?.accuracy ?? 0) * 100).toFixed(1)}%
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono">
                    vs. {(results.baseline?.majority_class_accuracy * 100)?.toFixed(1)}%
                    baseline
                  </span>
                </div>
                <div className="p-4 rounded-xl glass-card">
                  <span className="text-xs text-slate-400 uppercase">F1 Weighted</span>
                  <div className="text-2xl font-bold text-cyan-400 mt-1 font-mono">
                    {(results.metrics?.f1_weighted ?? 0).toFixed(4)}
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono">
                    Macro: {(results.metrics?.f1_macro ?? 0).toFixed(4)}
                  </span>
                </div>
                <div className="p-4 rounded-xl glass-card">
                  <span className="text-xs text-slate-400 uppercase">ROC AUC</span>
                  <div className="text-2xl font-bold text-indigo-400 mt-1 font-mono">
                    {results.metrics?.roc_auc !== undefined
                      ? results.metrics.roc_auc.toFixed(4)
                      : "N/A"}
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono">
                    Test Rows: {results.rows?.test}
                  </span>
                </div>
                <div className="p-4 rounded-xl glass-card">
                  <span className="text-xs text-slate-400 uppercase">Fit Time</span>
                  <div className="text-2xl font-bold text-amber-400 mt-1 font-mono">
                    {results.timing?.fit_seconds?.toFixed(2)}s
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono">
                    Total: {results.timing?.total_seconds?.toFixed(1)}s
                  </span>
                </div>
              </>
            ) : (
              <>
                <div className="p-4 rounded-xl glass-card">
                  <span className="text-xs text-slate-400 uppercase">R² Score</span>
                  <div className="text-2xl font-bold text-emerald-400 mt-1 font-mono">
                    {(results.metrics?.r2 ?? 0).toFixed(4)}
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono">
                    Baseline: 0.00
                  </span>
                </div>
                <div className="p-4 rounded-xl glass-card">
                  <span className="text-xs text-slate-400 uppercase">MAE</span>
                  <div className="text-2xl font-bold text-cyan-400 mt-1 font-mono">
                    {(results.metrics?.mae ?? 0).toFixed(4)}
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono">
                    Mean Absolute Error
                  </span>
                </div>
                <div className="p-4 rounded-xl glass-card">
                  <span className="text-xs text-slate-400 uppercase">RMSE</span>
                  <div className="text-2xl font-bold text-indigo-400 mt-1 font-mono">
                    {(results.metrics?.rmse ?? 0).toFixed(4)}
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono">
                    Root Mean Squared Error
                  </span>
                </div>
                <div className="p-4 rounded-xl glass-card">
                  <span className="text-xs text-slate-400 uppercase">Fit Time</span>
                  <div className="text-2xl font-bold text-amber-400 mt-1 font-mono">
                    {results.timing?.fit_seconds?.toFixed(2)}s
                  </div>
                  <span className="text-[11px] text-slate-500 font-mono">
                    Total: {results.timing?.total_seconds?.toFixed(1)}s
                  </span>
                </div>
              </>
            )}
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Feature Importance Horizontal Bar Chart */}
            <div className="p-5 rounded-2xl glass-panel space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold text-white">
                  Feature Importance (Normalized)
                </h3>
                {results.feature_importance?.aggregated_by_original_column && (
                  <button
                    onClick={() => setFeatureAggToggle(!featureAggToggle)}
                    className="text-xs text-cyan-400 hover:underline"
                  >
                    {featureAggToggle ? "Show All Encodings" : "Aggregate by Column"}
                  </button>
                )}
              </div>

              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    layout="vertical"
                    data={
                      featureAggToggle
                        ? results.feature_importance?.aggregated_by_original_column?.slice(
                            0,
                            10
                          ) || []
                        : results.feature_importance?.features?.slice(0, 10) || []
                    }
                    margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis type="number" stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis
                      dataKey="feature"
                      type="category"
                      stroke="#64748b"
                      tick={{ fontSize: 10 }}
                      width={80}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#0f172a",
                        borderColor: "#334155",
                        borderRadius: "8px",
                        fontSize: "12px",
                      }}
                    />
                    <Bar dataKey="importance" fill="#06b6d4" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Classification: Confusion Matrix / ROC */}
            {results.task === "classification" && results.confusion_matrix && (
              <div className="p-5 rounded-2xl glass-panel space-y-4">
                <h3 className="text-sm font-semibold text-white">
                  Confusion Matrix Heatmap
                </h3>
                <div className="flex flex-col items-center justify-center h-64 overflow-x-auto">
                  <div className="text-xs text-slate-400 mb-2 font-mono">
                    Predicted Class →
                  </div>
                  <div className="flex items-center">
                    <div className="text-xs text-slate-400 -rotate-90 mr-2 font-mono whitespace-nowrap">
                      Actual Class →
                    </div>
                    <div className="grid gap-1.5">
                      {results.confusion_matrix.matrix.map((row, rIdx) => (
                        <div key={rIdx} className="flex gap-1.5">
                          {row.map((cell, cIdx) => {
                            const isDiagonal = rIdx === cIdx;
                            return (
                              <div
                                key={cIdx}
                                className={`w-16 h-14 rounded-lg flex flex-col items-center justify-center font-mono text-xs border ${
                                  isDiagonal
                                    ? "bg-emerald-950/70 border-emerald-600/80 text-emerald-300 font-bold"
                                    : "bg-slate-900 border-slate-800 text-slate-400"
                                }`}
                              >
                                <span className="text-sm">{cell}</span>
                                <span className="text-[9px] opacity-70">
                                  {results.confusion_matrix?.labels[rIdx]}→
                                  {results.confusion_matrix?.labels[cIdx]}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Regression: Actual vs Predicted Scatter */}
            {results.task === "regression" && results.predictions_sample && (
              <div className="p-5 rounded-2xl glass-panel space-y-4">
                <h3 className="text-sm font-semibold text-white">
                  Predicted vs Actual Scatter Plot
                </h3>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis
                        type="number"
                        dataKey="actual"
                        name="Actual"
                        stroke="#64748b"
                        tick={{ fontSize: 10 }}
                      />
                      <YAxis
                        type="number"
                        dataKey="predicted"
                        name="Predicted"
                        stroke="#64748b"
                        tick={{ fontSize: 10 }}
                      />
                      <Tooltip
                        cursor={{ strokeDasharray: "3 3" }}
                        contentStyle={{
                          backgroundColor: "#0f172a",
                          borderColor: "#334155",
                          borderRadius: "8px",
                          fontSize: "12px",
                        }}
                      />
                      <Scatter
                        name="Predictions"
                        data={results.predictions_sample.slice(0, 150)}
                        fill="#22d3ee"
                      />
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>

          {/* Preprocessing Summary Report */}
          {results.preprocessing_report?.excluded_columns && (
            <div className="p-4 rounded-xl glass-card space-y-2 text-xs">
              <span className="font-semibold text-slate-300">
                Automated Feature Pipeline Report:
              </span>
              <div className="flex flex-wrap gap-2 text-slate-400">
                {results.preprocessing_report.excluded_columns.map((ex, i) => (
                  <span
                    key={i}
                    className="px-2 py-1 rounded bg-slate-800 border border-slate-700/80 font-mono"
                  >
                    Excluded <strong>{ex.column}</strong> ({ex.reason})
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ────────────────────────────────────────────────────────── */}
      {/* ARTIFACT DOWNLOADS SECTION */}
      {/* ────────────────────────────────────────────────────────── */}
      {job.status === "SUCCEEDED" && (
        <div className="p-6 rounded-2xl glass-panel space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Download className="w-5 h-5 text-cyan-400" />
              Trained Model Artifacts & Code
            </h2>
            <span className="text-xs text-slate-400 font-mono">
              Signed S3 URLs (Expire in 1 hr)
            </span>
          </div>

          {/* Security alert */}
          <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-800/60 text-amber-200 text-xs flex items-center gap-3">
            <ShieldAlert className="w-5 h-5 text-amber-400 flex-shrink-0" />
            <span>
              <strong>Security Notice:</strong> Python joblib files execute arbitrary code when deserialized. Only load model artifacts produced by trusted pipelines matching pinned package dependencies.
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 pt-2">
            {[
              {
                id: "model.joblib",
                label: "Trained Pipeline",
                file: "model.joblib",
                desc: "Complete fitted Scikit-Learn/XGBoost pipeline",
                url: artifacts?.model_joblib,
              },
              {
                id: "predict_example.py",
                label: "Inference Script",
                file: "predict_example.py",
                desc: "Standalone offline prediction script",
                url: artifacts?.predict_example_py,
              },
              {
                id: "metrics.json",
                label: "Metrics & Scores",
                file: "metrics.json",
                desc: "Raw JSON evaluation metrics",
                url: artifacts?.metrics_json,
              },
              {
                id: "model_card.md",
                label: "Model Card",
                file: "model_card.md",
                desc: "Markdown documentation & provenance",
                url: artifacts?.model_card_md,
              },
              {
                id: "requirements.txt",
                label: "Pinned Dependencies",
                file: "requirements.txt",
                desc: "Exact package versions for runtime",
                url: artifacts?.requirements_txt,
              },
              {
                id: "logs.txt",
                label: "Training Logs",
                file: "logs.txt",
                desc: "Full container stdout/stderr output",
                url: artifacts?.logs_txt,
              },
            ].map((art) => (
              <a
                key={art.id}
                href={art.url || "#"}
                target="_blank"
                rel="noreferrer"
                download={art.file}
                className={`p-3.5 rounded-xl border flex items-center justify-between transition-all ${
                  art.url
                    ? "bg-slate-900/80 border-slate-700/80 hover:border-cyan-500 hover:bg-cyan-950/20 text-slate-200"
                    : "bg-slate-900/30 border-slate-800 text-slate-500 pointer-events-none"
                }`}
              >
                <div className="space-y-0.5">
                  <div className="font-semibold text-xs text-white">{art.label}</div>
                  <div className="text-[11px] font-mono text-cyan-400">{art.file}</div>
                  <div className="text-[10px] text-slate-400">{art.desc}</div>
                </div>
                <Download className="w-4 h-4 text-slate-400 group-hover:text-cyan-400" />
              </a>
            ))}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────── */}
      {/* LIVE / STORED LOGS PANEL */}
      {/* ────────────────────────────────────────────────────────── */}
      <div className="p-6 rounded-2xl glass-panel space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Terminal className="w-5 h-5 text-cyan-400" />
            <h2 className="text-base font-semibold text-white">Execution Logs</h2>
            {!isTerminal && (
              <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-cyan-400 bg-cyan-950/70 border border-cyan-800/80 px-1.5 py-0.5 rounded">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                Live Stream
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="accent-cyan-500"
              />
              Auto-scroll
            </label>
            <button
              onClick={copyLogsToClipboard}
              className="p-1.5 rounded bg-slate-800 text-slate-300 hover:text-white text-xs flex items-center gap-1"
            >
              <Copy className="w-3.5 h-3.5" />
              {copiedLog ? "Copied!" : "Copy"}
            </button>
          </div>
        </div>

        <div className="bg-[#050811] border border-slate-800 rounded-xl p-4 font-mono text-xs text-slate-300 h-80 overflow-y-auto leading-relaxed select-text">
          {logData?.logs ? (
            <pre className="whitespace-pre-wrap">{logData.logs}</pre>
          ) : (
            <div className="text-slate-600 italic">
              {job.status === "QUEUED"
                ? "Job is queued. Logs will stream once the EC2 worker launches container."
                : "No logs recorded yet."}
            </div>
          )}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  );
};
