import React, { useState, useRef } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchDatasets,
  initiateDatasetUpload,
  uploadFileToPresignedPost,
  deleteDataset,
} from "@/lib/api";
import { DatasetStatusBadge } from "@/components/StatusBadge";
import { formatBytes, formatDate } from "@/utils/formatters";
import {
  UploadCloud,
  FileText,
  Trash2,
  Sparkles,
  AlertCircle,
  Database,
  ArrowRight,
  X,
} from "lucide-react";

export const Datasets: React.FC = () => {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [datasetName, setDatasetName] = useState("");
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Poll datasets every 3s if any is profiling or uploading, else 15s
  const { data: datasets = [], isLoading } = useQuery({
    queryKey: ["datasets"],
    queryFn: fetchDatasets,
    refetchInterval: (query) => {
      const busy = query.state.data?.some(
        (d) => d.status === "UPLOADING" || d.status === "PROFILING" || d.status === "PENDING_UPLOAD"
      );
      return busy ? 2000 : 15000;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteDataset(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      queryClient.invalidateQueries({ queryKey: ["quotas"] });
      setDeletingId(null);
    },
    onError: (err: any) => {
      alert(err.message || "Failed to delete dataset");
      setDeletingId(null);
    },
  });

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const validateAndSelectFile = (file: File) => {
    setUploadError(null);
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setUploadError("Only .csv files are supported.");
      return;
    }
    const MAX_SIZE = 100 * 1024 * 1024; // 100 MB
    if (file.size > MAX_SIZE) {
      setUploadError("File size exceeds 100 MB limit.");
      return;
    }
    setSelectedFile(file);
    if (!datasetName) {
      const cleanName = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
      setDatasetName(cleanName.charAt(0).toUpperCase() + cleanName.slice(1));
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSelectFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSelectFile(e.target.files[0]);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) return;

    try {
      setUploadError(null);
      setUploadProgress(0);

      // 1. Get presigned POST from API
      const presigned = await initiateDatasetUpload({
        name: datasetName || selectedFile.name,
        filename: selectedFile.name,
        size_bytes: selectedFile.size,
      });

      // 2. Direct S3 upload with progress
      await uploadFileToPresignedPost(presigned, selectedFile, (pct) => {
        setUploadProgress(pct);
      });

      // Reset form and refresh datasets
      setSelectedFile(null);
      setDatasetName("");
      setUploadProgress(null);
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      queryClient.invalidateQueries({ queryKey: ["quotas"] });
    } catch (err: any) {
      setUploadError(err.message || "Upload failed. Please try again.");
      setUploadProgress(null);
    }
  };

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
            <Database className="w-6 h-6 text-cyan-400" />
            Dataset Management
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Upload CSV datasets (up to 100 MB). CloudTrain automatically detects types, missing values, and columns.
          </p>
        </div>
        <div className="text-xs text-slate-400 font-mono bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-800 self-start sm:self-auto">
          Quota: {datasets.length} / 10 Datasets
        </div>
      </div>

      {/* Upload Zone */}
      <div className="p-6 rounded-2xl glass-panel space-y-5">
        <h2 className="text-base font-semibold text-white flex items-center gap-2">
          <UploadCloud className="w-5 h-5 text-cyan-400" />
          Direct-to-S3 CSV Uploader
        </h2>

        {uploadError && (
          <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-sm flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-medium">Upload Error:</span>
              <p className="text-rose-200/90 text-xs">{uploadError}</p>
            </div>
          </div>
        )}

        <form onSubmit={handleUpload} className="space-y-4">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={handleFileChange}
          />

          {!selectedFile ? (
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`p-10 border-2 border-dashed rounded-xl flex flex-col items-center justify-center text-center cursor-pointer transition-all duration-200 ${
                dragActive
                  ? "border-cyan-400 bg-cyan-950/20 scale-[0.99]"
                  : "border-slate-700/80 hover:border-slate-600 bg-slate-900/30 hover:bg-slate-900/50"
              }`}
            >
              <div className="w-14 h-14 rounded-full bg-slate-800/80 border border-slate-700 flex items-center justify-center mb-3 text-cyan-400 group-hover:scale-105 transition-transform">
                <UploadCloud className="w-7 h-7" />
              </div>
              <p className="text-sm font-medium text-slate-200">
                Drag and drop your CSV file here, or{" "}
                <span className="text-cyan-400 underline">browse</span>
              </p>
              <p className="text-xs text-slate-500 mt-1">
                CSV format, up to 100 MB per dataset
              </p>
            </div>
          ) : (
            <div className="p-5 rounded-xl bg-slate-900/80 border border-slate-700 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-cyan-950/80 border border-cyan-800/60 flex items-center justify-center text-cyan-400">
                    <FileText className="w-5 h-5" />
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-white truncate max-w-sm">
                      {selectedFile.name}
                    </h4>
                    <span className="text-xs text-slate-400 font-mono">
                      {formatBytes(selectedFile.size)}
                    </span>
                  </div>
                </div>
                {uploadProgress === null && (
                  <button
                    type="button"
                    onClick={() => setSelectedFile(null)}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>

              {uploadProgress === null ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
                  <div>
                    <label className="block text-xs font-medium text-slate-300 mb-1">
                      Dataset Display Name
                    </label>
                    <input
                      type="text"
                      value={datasetName}
                      onChange={(e) => setDatasetName(e.target.value)}
                      placeholder="e.g. Customer Churn Q3"
                      className="w-full px-3 py-2 rounded-lg bg-slate-800 border border-slate-700 text-white text-sm focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                  <div className="flex items-end">
                    <button
                      type="submit"
                      className="w-full py-2 px-4 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white text-sm font-medium shadow-md shadow-cyan-500/25 transition-all"
                    >
                      Upload to S3 & Start Profiling
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-2 pt-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-cyan-400 font-medium">
                      Uploading directly to private S3 bucket...
                    </span>
                    <span className="font-mono text-slate-300">{uploadProgress}%</span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-cyan-500 h-full rounded-full transition-all duration-150"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </form>
      </div>

      {/* Datasets Table */}
      <div className="space-y-4">
        <h2 className="text-lg font-semibold text-white">Your Datasets</h2>

        {isLoading ? (
          <div className="p-8 rounded-xl glass-card text-center text-slate-400">
            <div className="w-6 h-6 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
            Loading datasets...
          </div>
        ) : datasets.length === 0 ? (
          <div className="p-12 rounded-xl glass-card text-center space-y-3 border-dashed border-slate-800">
            <p className="text-sm text-slate-400">No datasets found in your account.</p>
            <p className="text-xs text-slate-500">
              Upload a CSV file above or use our pre-built samples to begin.
            </p>
          </div>
        ) : (
          <div className="rounded-xl glass-card border border-slate-800 overflow-hidden shadow-lg">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-900/80 text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="py-3 px-4 font-medium">Dataset</th>
                    <th className="py-3 px-4 font-medium">Status</th>
                    <th className="py-3 px-4 font-medium">Dimensions</th>
                    <th className="py-3 px-4 font-medium">File Size</th>
                    <th className="py-3 px-4 font-medium">Uploaded</th>
                    <th className="py-3 px-4 font-medium text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {datasets.map((ds) => (
                    <tr
                      key={ds.dataset_id}
                      className="hover:bg-slate-800/40 transition-colors group"
                    >
                      <td className="py-3.5 px-4">
                        <Link
                          to={`/datasets/${ds.dataset_id}`}
                          className="font-medium text-slate-200 hover:text-cyan-400 transition-colors flex items-center gap-2"
                        >
                          <FileText className="w-4 h-4 text-cyan-500 flex-shrink-0" />
                          <div>
                            <div>{ds.name}</div>
                            <span className="text-[11px] font-mono text-slate-500">
                              {ds.filename}
                            </span>
                          </div>
                        </Link>
                      </td>
                      <td className="py-3.5 px-4">
                        <DatasetStatusBadge status={ds.status} size="sm" />
                        {ds.error && (
                          <div className="text-[11px] text-rose-400 mt-1 max-w-xs">
                            {ds.error.message}
                          </div>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-slate-300 font-mono text-xs">
                        {ds.profile?.row_count !== undefined
                          ? `${ds.profile.row_count.toLocaleString()} rows × ${
                              ds.profile.column_count
                            } cols`
                          : "—"}
                      </td>
                      <td className="py-3.5 px-4 text-xs font-mono text-slate-400">
                        {formatBytes(ds.size_bytes)}
                      </td>
                      <td className="py-3.5 px-4 text-xs text-slate-400">
                        {formatDate(ds.created_at)}
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {ds.status === "READY" && (
                            <Link
                              to={`/train?dataset=${ds.dataset_id}`}
                              className="px-2.5 py-1 rounded bg-cyan-950/60 hover:bg-cyan-900/80 text-cyan-300 border border-cyan-800/60 text-xs font-medium flex items-center gap-1 transition-colors"
                            >
                              <Sparkles className="w-3 h-3" />
                              Train
                            </Link>
                          )}
                          <Link
                            to={`/datasets/${ds.dataset_id}`}
                            className="p-1.5 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                            title="View Profile"
                          >
                            <ArrowRight className="w-4 h-4" />
                          </Link>
                          <button
                            onClick={() => {
                              if (
                                confirm(
                                  `Are you sure you want to delete dataset "${ds.name}"?`
                                )
                              ) {
                                setDeletingId(ds.dataset_id);
                                deleteMutation.mutate(ds.dataset_id);
                              }
                            }}
                            disabled={deletingId === ds.dataset_id}
                            className="p-1.5 rounded text-slate-400 hover:text-rose-400 hover:bg-rose-950/30 transition-colors"
                            title="Delete Dataset"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
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
