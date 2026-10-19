import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchJobs, cancelJob, deleteJob } from "@/lib/api";
import { JobStatusBadge } from "@/components/StatusBadge";
import { formatDuration, formatDate } from "@/utils/formatters";
import {
  BrainCircuit,
  Search,
  Filter,
  Sparkles,
  ArrowRight,
  XCircle,
  Trash2,
  RefreshCw,
} from "lucide-react";

export const Jobs: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  const {
    data: jobs = [],
    isLoading,
    refetch,
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

  const cancelMutation = useMutation({
    mutationFn: (id: string) => cancelJob(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["quotas"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteJob(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["quotas"] });
    },
  });

  // Filtering
  const filteredJobs = jobs.filter((job) => {
    const matchesSearch =
      job.name?.toLowerCase().includes(search.toLowerCase()) ||
      job.job_id.toLowerCase().includes(search.toLowerCase()) ||
      job.config?.model?.id.toLowerCase().includes(search.toLowerCase());

    if (!matchesSearch) return false;

    if (statusFilter === "ALL") return true;
    if (statusFilter === "ACTIVE") {
      return ["QUEUED", "PROVISIONING", "RUNNING", "UPLOADING"].includes(job.status);
    }
    return job.status === statusFilter;
  });

  const totalPages = Math.max(1, Math.ceil(filteredJobs.length / pageSize));
  const paginatedJobs = filteredJobs.slice(
    (currentPage - 1) * pageSize,
    currentPage * pageSize
  );

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
            <BrainCircuit className="w-6 h-6 text-cyan-400" />
            Training Jobs History
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Monitor, inspect, cancel, and review outputs of all ML training workloads.
          </p>
        </div>
        <Link
          to="/train"
          className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-medium text-sm transition-all shadow-md shadow-cyan-500/25 self-start sm:self-auto"
        >
          <Sparkles className="w-4 h-4 fill-white/20" />
          New Training
        </Link>
      </div>

      {/* Filter and Search Controls */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 p-4 rounded-xl glass-panel">
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setCurrentPage(1);
            }}
            placeholder="Search by job name, model, or ID..."
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-slate-900 border border-slate-700 text-sm text-white focus:outline-none focus:border-cyan-500"
          />
        </div>

        <div className="flex items-center gap-2 overflow-x-auto pb-1 md:pb-0">
          <Filter className="w-4 h-4 text-slate-400 flex-shrink-0" />
          {[
            { id: "ALL", label: "All" },
            { id: "ACTIVE", label: "Active" },
            { id: "SUCCEEDED", label: "Succeeded" },
            { id: "FAILED", label: "Failed" },
            { id: "CANCELLED", label: "Cancelled" },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => {
                setStatusFilter(item.id);
                setCurrentPage(1);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors ${
                statusFilter === item.id
                  ? "bg-cyan-950/70 text-cyan-300 border border-cyan-800/80"
                  : "bg-slate-900 text-slate-400 hover:text-white border border-slate-800"
              }`}
            >
              {item.label}
            </button>
          ))}
          <button
            onClick={() => refetch()}
            className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white"
            title="Refresh jobs"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Jobs Table */}
      {isLoading ? (
        <div className="p-12 text-center text-slate-400">Loading jobs...</div>
      ) : paginatedJobs.length === 0 ? (
        <div className="p-12 rounded-xl glass-card text-center space-y-3 border-dashed border-slate-800">
          <p className="text-sm text-slate-400">No training jobs match your criteria.</p>
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
                  <th className="py-3 px-4 font-medium">Compute</th>
                  <th className="py-3 px-4 font-medium">Duration</th>
                  <th className="py-3 px-4 font-medium">Created</th>
                  <th className="py-3 px-4 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-xs">
                {paginatedJobs.map((job) => (
                  <tr
                    key={job.job_id}
                    className="hover:bg-slate-800/40 transition-colors group cursor-pointer"
                    onClick={() => navigate(`/jobs/${job.job_id}`)}
                  >
                    <td className="py-3.5 px-4 font-medium text-slate-200">
                      <div className="flex flex-col">
                        <span className="text-sm font-semibold group-hover:text-cyan-400 transition-colors">
                          {job.name || `Job ${job.job_id.slice(0, 8)}`}
                        </span>
                        <span className="text-[11px] font-mono text-slate-500">
                          {job.job_id}
                        </span>
                      </div>
                    </td>
                    <td className="py-3.5 px-4 text-slate-300 font-mono">
                      <span className="capitalize">
                        {job.config?.model?.id?.replace(/_/g, " ") || "Model"}
                      </span>
                      <span className="text-slate-500 block text-[11px] capitalize">
                        {job.config?.task || "classification"}
                      </span>
                    </td>
                    <td className="py-3.5 px-4">
                      <JobStatusBadge status={job.status} size="sm" />
                    </td>
                    <td className="py-3.5 px-4">
                      <div className="w-32 space-y-1">
                        <div className="flex items-center justify-between text-[11px]">
                          <span className="text-slate-400 truncate max-w-[85px]">
                            {job.stage || "Pending"}
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
                    <td className="py-3.5 px-4 font-mono uppercase text-slate-400">
                      {job.compute_size}
                    </td>
                    <td className="py-3.5 px-4 font-mono text-slate-400">
                      {formatDuration(job.duration_seconds)}
                    </td>
                    <td className="py-3.5 px-4 text-slate-400">
                      {formatDate(job.created_at)}
                    </td>
                    <td
                      className="py-3.5 px-4 text-right"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex items-center justify-end gap-2">
                        {["QUEUED", "PROVISIONING", "RUNNING"].includes(job.status) && (
                          <button
                            onClick={() => cancelMutation.mutate(job.job_id)}
                            className="p-1 rounded text-slate-400 hover:text-amber-400 hover:bg-amber-950/30 transition-colors"
                            title="Cancel Job"
                          >
                            <XCircle className="w-4 h-4" />
                          </button>
                        )}
                        {["SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"].includes(
                          job.status
                        ) && (
                          <button
                            onClick={() => {
                              if (confirm(`Delete job records permanently?`)) {
                                deleteMutation.mutate(job.job_id);
                              }
                            }}
                            className="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-rose-950/30 transition-colors"
                            title="Delete Job"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        )}
                        <Link
                          to={`/jobs/${job.job_id}`}
                          className="p-1 rounded text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition-colors"
                        >
                          <ArrowRight className="w-4 h-4" />
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="p-3 bg-slate-900/60 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <span>
                Showing {(currentPage - 1) * pageSize + 1} to{" "}
                {Math.min(currentPage * pageSize, filteredJobs.length)} of{" "}
                {filteredJobs.length} jobs
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="px-2.5 py-1 rounded bg-slate-800 disabled:opacity-40 hover:bg-slate-700"
                >
                  Prev
                </button>
                <span className="px-2">
                  {currentPage} of {totalPages}
                </span>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="px-2.5 py-1 rounded bg-slate-800 disabled:opacity-40 hover:bg-slate-700"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
