import React from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchDataset, deleteDataset } from "@/lib/api";
import { DatasetStatusBadge } from "@/components/StatusBadge";
import { formatBytes, formatDate } from "@/utils/formatters";
import {
  Database,
  ArrowLeft,
  Sparkles,
  Trash2,
  AlertTriangle,
  FileSpreadsheet,
  Table,
} from "lucide-react";

export const DatasetDetail: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: dataset, isLoading, error } = useQuery({
    queryKey: ["dataset", id],
    queryFn: () => fetchDataset(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "UPLOADING" || status === "PROFILING" ? 3000 : false;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteDataset(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      queryClient.invalidateQueries({ queryKey: ["quotas"] });
      navigate("/datasets");
    },
  });

  if (isLoading) {
    return (
      <div className="p-12 text-center text-slate-400">
        <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        Loading dataset profile...
      </div>
    );
  }

  if (error || !dataset) {
    return (
      <div className="p-8 rounded-2xl glass-panel text-center space-y-4">
        <h2 className="text-lg font-semibold text-rose-400">Dataset Not Found</h2>
        <p className="text-xs text-slate-400">
          The requested dataset could not be loaded or has been deleted.
        </p>
        <Link
          to="/datasets"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 text-slate-200 text-xs font-medium hover:bg-slate-700"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Datasets
        </Link>
      </div>
    );
  }

  const profile = dataset.profile;

  const getTypeBadgeClass = (inferred: string) => {
    switch (inferred) {
      case "numeric":
        return "bg-cyan-950/60 text-cyan-300 border-cyan-800/60";
      case "categorical":
        return "bg-purple-950/60 text-purple-300 border-purple-800/60";
      case "boolean":
        return "bg-blue-950/60 text-blue-300 border-blue-800/60";
      case "datetime":
        return "bg-emerald-950/60 text-emerald-300 border-emerald-800/60";
      case "id_like":
        return "bg-slate-800 text-slate-400 border-slate-700";
      case "constant":
        return "bg-rose-950/60 text-rose-300 border-rose-800/60";
      case "text":
        return "bg-amber-950/60 text-amber-300 border-amber-800/60";
      default:
        return "bg-slate-800 text-slate-300 border-slate-700";
    }
  };

  return (
    <div className="space-y-8">
      {/* Back button & Action Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <Link
            to="/datasets"
            className="text-xs text-slate-400 hover:text-cyan-400 flex items-center gap-1.5 transition-colors mb-2"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Datasets
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <Database className="w-6 h-6 text-cyan-400" />
              {dataset.name}
            </h1>
            <DatasetStatusBadge status={dataset.status} />
          </div>
          <div className="flex items-center gap-4 text-xs text-slate-400 font-mono">
            <span>Filename: {dataset.filename}</span>
            <span>•</span>
            <span>Size: {formatBytes(dataset.size_bytes)}</span>
            <span>•</span>
            <span>Uploaded: {formatDate(dataset.created_at)}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {dataset.status === "READY" && (
            <Link
              to={`/train?dataset=${dataset.dataset_id}`}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-medium text-sm transition-all shadow-lg shadow-cyan-500/25"
            >
              <Sparkles className="w-4 h-4 fill-white/20" />
              Train Model on Dataset
            </Link>
          )}
          <button
            onClick={() => {
              if (confirm(`Delete dataset "${dataset.name}" permanently?`)) {
                deleteMutation.mutate();
              }
            }}
            className="p-2.5 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 hover:text-rose-400 hover:border-rose-900/50 transition-colors"
            title="Delete dataset"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Profiling status alert if still processing */}
      {(dataset.status === "UPLOADING" || dataset.status === "PROFILING") && (
        <div className="p-5 rounded-2xl glass-panel border border-cyan-800/60 flex items-center gap-3 text-cyan-300">
          <div className="w-5 h-5 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
          <div>
            <h4 className="text-sm font-semibold">Profiling In Progress...</h4>
            <p className="text-xs text-cyan-400/80">
              CloudTrain is inspecting dataset schemas, column distributions, and missing rates.
            </p>
          </div>
        </div>
      )}

      {/* Warnings Banner if present */}
      {profile?.warnings && profile.warnings.length > 0 && (
        <div className="p-4 rounded-xl bg-amber-950/30 border border-amber-800/60 space-y-2">
          <div className="flex items-center gap-2 text-amber-300 text-sm font-semibold">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            Dataset Heuristic Warnings ({profile.warnings.length})
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-amber-200/90">
            {profile.warnings.map((w, i) => (
              <div
                key={i}
                className="p-2 rounded bg-amber-900/20 border border-amber-800/40 flex items-start gap-2"
              >
                <span className="font-mono text-[11px] bg-amber-950/60 px-1 rounded text-amber-300">
                  {w.column || "Dataset"}
                </span>
                <span>{w.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Columns Schema & Statistics Table */}
      {profile && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <FileSpreadsheet className="w-5 h-5 text-indigo-400" />
              Column Profiles & Types
            </h2>
            <div className="text-xs text-slate-400 font-mono">
              {profile.row_count.toLocaleString()} rows × {profile.column_count} columns
            </div>
          </div>

          <div className="rounded-xl glass-card border border-slate-800 overflow-hidden shadow-lg">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4 font-medium">Column Name</th>
                    <th className="py-3 px-4 font-medium">Inferred Type</th>
                    <th className="py-3 px-4 font-medium">Missing</th>
                    <th className="py-3 px-4 font-medium">Unique</th>
                    <th className="py-3 px-4 font-medium">Sample Values</th>
                    <th className="py-3 px-4 font-medium">Summary Stats</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 text-xs">
                  {profile.columns.map((col) => (
                    <tr key={col.name} className="hover:bg-slate-800/30">
                      <td className="py-3 px-4 font-mono font-medium text-slate-200">
                        {col.name}
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`px-2 py-0.5 rounded text-[11px] font-medium border uppercase tracking-wider ${getTypeBadgeClass(
                            col.inferred_type
                          )}`}
                        >
                          {col.inferred_type}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono">
                        <span
                          className={
                            col.missing_pct > 0.05
                              ? "text-amber-400 font-semibold"
                              : "text-slate-400"
                          }
                        >
                          {(col.missing_pct * 100).toFixed(1)}%
                        </span>
                        <span className="text-slate-500 ml-1">
                          ({col.missing_count})
                        </span>
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-300">
                        {col.unique_count.toLocaleString()}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1 max-w-xs">
                          {col.sample_values?.slice(0, 3).map((val, vi) => (
                            <span
                              key={vi}
                              className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700/80 text-slate-300 font-mono text-[11px] truncate max-w-[90px]"
                            >
                              {String(val)}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 px-4 font-mono text-slate-400">
                        {col.stats?.mean !== undefined ? (
                          <div className="space-x-2 text-[11px]">
                            <span>μ: {col.stats.mean.toFixed(2)}</span>
                            <span>σ: {col.stats.std?.toFixed(2)}</span>
                            <span>
                              [{col.stats.min} ... {col.stats.max}]
                            </span>
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* 20-Row Preview Table */}
      {profile?.preview && profile.preview.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white flex items-center gap-2">
              <Table className="w-5 h-5 text-cyan-400" />
              Raw Data Preview (First 20 Rows)
            </h2>
            <span className="text-xs text-slate-400 font-mono">
              Showing {profile.preview.length} rows
            </span>
          </div>

          <div className="rounded-xl glass-card border border-slate-800 overflow-hidden shadow-lg">
            <div className="overflow-x-auto max-h-96">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-slate-900/90 text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-800 sticky top-0 z-10">
                  <tr>
                    <th className="py-2.5 px-3 bg-slate-900/90 border-r border-slate-800 text-slate-500 w-12 text-center">
                      #
                    </th>
                    {profile.columns.map((c) => (
                      <th
                        key={c.name}
                        className="py-2.5 px-3 font-semibold text-slate-300 border-r border-slate-800/60 whitespace-nowrap"
                      >
                        {c.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {profile.preview.map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/40">
                      <td className="py-2 px-3 border-r border-slate-800 text-slate-500 text-center select-none">
                        {idx + 1}
                      </td>
                      {profile.columns.map((c) => (
                        <td
                          key={c.name}
                          className="py-2 px-3 text-slate-300 border-r border-slate-800/40 whitespace-nowrap max-w-xs truncate"
                        >
                          {row[c.name] === null || row[c.name] === undefined ? (
                            <span className="text-slate-600 italic">null</span>
                          ) : (
                            String(row[c.name])
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
