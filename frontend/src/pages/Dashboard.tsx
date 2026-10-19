import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { fetchJobs, fetchQuotas, fetchDatasets } from "@/lib/api";
import { JobStatusBadge } from "@/components/StatusBadge";
import { formatDuration, formatDate } from "@/utils/formatters";
import {
  Sparkles,
  Database,
  BrainCircuit,
  Activity,
  CheckCircle2,
  HardDrive,
  ShieldAlert,
  ArrowRight,
  RefreshCw,
} from "lucide-react";

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();

  const { data: quotas } = useQuery({
    queryKey: ["quotas"],
    queryFn: fetchQuotas,
    refetchInterval: 15000,
  });

  const {
    data: jobs = [],
    isLoading: loadingJobs,
    refetch: refetchJobs,
  } = useQuery({
    queryKey: ["jobs"],
    queryFn: () => fetchJobs(),
    refetchInterval: (query) => {
      const active = query.state.data?.some((j) =>
        ["QUEUED", "PROVISIONING", "RUNNING", "UPLOADING"].includes(j.status)
      );
      return active ? 5000 : 30000;
    },
  });

  const { data: datasets = [] } = useQuery({
    queryKey: ["datasets"],
    queryFn: fetchDatasets,
  });

  const succeededJobs = jobs.filter((j) => j.status === "SUCCEEDED").length;
  const activeJobs = jobs.filter((j) =>
    ["QUEUED", "PROVISIONING", "RUNNING", "UPLOADING"].includes(j.status)
  ).length;

  return (
    <div className="space-y-8">
      {/* Hero Welcome & Action Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-6 rounded-2xl glass-panel relative overflow-hidden">
        <div className="space-y-1.5 z-10">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-white">
              CloudTrain Dashboard
            </h1>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-950/60 text-emerald-400 border border-emerald-800/60">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Infrastructure Ready
            </span>
          </div>
          <p className="text-sm text-slate-400 max-w-xl">
            Zero-cost, self-terminating machine learning on AWS. Train tabular models with automatic preprocessing and full explainability.
          </p>
        </div>

        <div className="flex items-center gap-3 z-10">
          <Link
            to="/datasets"
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800/90 hover:bg-slate-700/90 text-slate-200 border border-slate-700 text-sm font-medium transition-all shadow-sm"
          >
            <Database className="w-4 h-4 text-cyan-400" />
            Upload Dataset
          </Link>
          <Link
            to="/train"
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-medium text-sm transition-all shadow-lg shadow-cyan-500/25 hover:shadow-cyan-500/35"
          >
            <Sparkles className="w-4 h-4 fill-white/20" />
            New Training
          </Link>
        </div>
      </div>

      {/* Quota & Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Active Jobs Quota */}
        <div className="p-5 rounded-xl glass-card relative group hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Active Jobs
            </span>
            <Activity className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">
              {quotas?.active_jobs?.count ?? activeJobs}
            </span>
            <span className="text-xs text-slate-500">
              / {quotas?.active_jobs?.max ?? 3} allowed
            </span>
          </div>
          <div className="mt-3 w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-cyan-500 h-full rounded-full transition-all duration-300"
              style={{
                width: `${Math.min(
                  100,
                  (((quotas?.active_jobs?.count ?? activeJobs) /
                    (quotas?.active_jobs?.max || 3)) *
                    100)
                )}%`,
              }}
            />
          </div>
        </div>

        {/* Datasets Quota */}
        <div className="p-5 rounded-xl glass-card relative group hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Stored Datasets
            </span>
            <HardDrive className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">
              {quotas?.datasets?.count ?? datasets.length}
            </span>
            <span className="text-xs text-slate-500">
              / {quotas?.datasets?.max ?? 10} quota
            </span>
          </div>
          <div className="mt-3 w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-indigo-500 h-full rounded-full transition-all duration-300"
              style={{
                width: `${Math.min(
                  100,
                  (((quotas?.datasets?.count ?? datasets.length) /
                    (quotas?.datasets?.max || 10)) *
                    100)
                )}%`,
              }}
            />
          </div>
        </div>

        {/* Succeeded Models */}
        <div className="p-5 rounded-xl glass-card relative group hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Trained Models
            </span>
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">{succeededJobs}</span>
            <span className="text-xs text-slate-500">ready to deploy</span>
          </div>
          <p className="mt-3 text-xs text-slate-400 truncate">
            {jobs.length} total training runs initiated
          </p>
        </div>

        {/* Cost Guardrail Monitor */}
        <div className="p-5 rounded-xl glass-card relative group hover:border-slate-700 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Cost Guardrail
            </span>
            <ShieldAlert className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white">$0.00</span>
            <span className="text-xs text-slate-500">/ $10.00 budget</span>
          </div>
          <p className="mt-3 text-xs text-emerald-400/90 font-mono">
            Zero NAT/ALB • Terminating EC2
          </p>
        </div>
      </div>

      {/* Recent Jobs Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-white">Recent Training Runs</h2>
            <button
              onClick={() => refetchJobs()}
              className="p-1 text-slate-400 hover:text-white rounded transition-colors"
              title="Refresh jobs"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
          {jobs.length > 5 && (
            <Link
              to="/jobs"
              className="text-xs font-medium text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
            >
              View all ({jobs.length})
              <ArrowRight className="w-3 h-3" />
            </Link>
          )}
        </div>

        {loadingJobs ? (
          <div className="p-8 rounded-xl glass-card text-center text-slate-400">
            <div className="w-6 h-6 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            Loading training jobs...
          </div>
        ) : jobs.length === 0 ? (
          <div className="p-12 rounded-xl glass-card text-center space-y-4 border-dashed border-slate-800">
            <div className="w-12 h-12 rounded-full bg-slate-800/80 flex items-center justify-center mx-auto text-slate-400">
              <BrainCircuit className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <h3 className="text-base font-medium text-slate-200">No training jobs yet</h3>
              <p className="text-xs text-slate-400 max-w-sm mx-auto">
                Upload a CSV dataset and run the 7-step wizard to train your first model on self-terminating EC2.
              </p>
            </div>
            <Link
              to="/train"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-medium transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5" />
              Launch First Training Job
            </Link>
          </div>
        ) : (
          <div className="rounded-xl glass-card border border-slate-800 overflow-hidden shadow-lg">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4 font-medium">Job Name</th>
                    <th className="py-3 px-4 font-medium">Model</th>
                    <th className="py-3 px-4 font-medium">Status</th>
                    <th className="py-3 px-4 font-medium">Progress / Stage</th>
                    <th className="py-3 px-4 font-medium">Duration</th>
                    <th className="py-3 px-4 font-medium">Created</th>
                    <th className="py-3 px-4 font-medium text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {jobs.slice(0, 6).map((job) => (
                    <tr
                      key={job.job_id}
                      onClick={() => navigate(`/jobs/${job.job_id}`)}
                      className="hover:bg-slate-800/40 cursor-pointer transition-colors group"
                    >
                      <td className="py-3.5 px-4 font-medium text-slate-200">
                        <div className="flex flex-col">
                          <span className="group-hover:text-cyan-400 transition-colors">
                            {job.name || `Job ${job.job_id.slice(0, 8)}`}
                          </span>
                          <span className="text-[11px] font-mono text-slate-500">
                            {job.job_id}
                          </span>
                        </div>
                      </td>
                      <td className="py-3.5 px-4 text-slate-300">
                        <span className="capitalize">
                          {job.config?.model?.id?.replace(/_/g, " ") || "Custom"}
                        </span>
                        <span className="text-xs text-slate-500 ml-1.5">
                          ({job.compute_size})
                        </span>
                      </td>
                      <td className="py-3.5 px-4">
                        <JobStatusBadge status={job.status} size="sm" />
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="w-36 space-y-1">
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="text-slate-400 truncate max-w-[90px]">
                              {job.stage || "Idle"}
                            </span>
                            <span className="text-slate-500 font-mono">
                              {job.progress}%
                            </span>
                          </div>
                          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
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
                        </div>
                      </td>
                      <td className="py-3.5 px-4 text-xs font-mono text-slate-400">
                        {formatDuration(job.duration_seconds)}
                      </td>
                      <td className="py-3.5 px-4 text-xs text-slate-400">
                        {formatDate(job.created_at)}
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <span className="text-xs text-cyan-400 group-hover:translate-x-1 inline-flex items-center gap-1 transition-transform">
                          Details
                          <ArrowRight className="w-3.5 h-3.5" />
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
