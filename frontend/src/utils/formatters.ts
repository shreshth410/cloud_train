import { JobStatus, DatasetStatus } from "@/types";

export function formatBytes(bytes: number, decimals = 1): string {
  if (!bytes || bytes <= 0) return "0 B";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

export function formatDuration(seconds?: number): string {
  if (seconds === undefined || seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins < 60) return `${mins}m ${secs}s`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return `${hours}h ${remMins}m`;
}

export function formatDate(isoString?: string): string {
  if (!isoString) return "—";
  try {
    const d = new Date(isoString);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(d);
  } catch {
    return isoString;
  }
}

export interface StatusBadgeConfig {
  label: string;
  badgeClass: string;
  dotClass: string;
  isAnimated: boolean;
}

export function getJobStatusBadge(status: JobStatus): StatusBadgeConfig {
  switch (status) {
    case "QUEUED":
      return {
        label: "Queued",
        badgeClass: "bg-slate-800 text-slate-300 border-slate-700",
        dotClass: "bg-slate-400",
        isAnimated: false,
      };
    case "PROVISIONING":
      return {
        label: "Provisioning",
        badgeClass: "bg-amber-950/40 text-amber-300 border-amber-800/60",
        dotClass: "bg-amber-400",
        isAnimated: true,
      };
    case "RUNNING":
      return {
        label: "Running",
        badgeClass: "bg-cyan-950/40 text-cyan-300 border-cyan-800/60",
        dotClass: "bg-cyan-400",
        isAnimated: true,
      };
    case "UPLOADING":
      return {
        label: "Uploading Artifacts",
        badgeClass: "bg-blue-950/40 text-blue-300 border-blue-800/60",
        dotClass: "bg-blue-400",
        isAnimated: true,
      };
    case "SUCCEEDED":
      return {
        label: "Succeeded",
        badgeClass: "bg-emerald-950/40 text-emerald-300 border-emerald-800/60",
        dotClass: "bg-emerald-400",
        isAnimated: false,
      };
    case "FAILED":
      return {
        label: "Failed",
        badgeClass: "bg-rose-950/40 text-rose-300 border-rose-800/60",
        dotClass: "bg-rose-400",
        isAnimated: false,
      };
    case "CANCELLED":
      return {
        label: "Cancelled",
        badgeClass: "bg-zinc-800/80 text-zinc-400 border-zinc-700/60",
        dotClass: "bg-zinc-400",
        isAnimated: false,
      };
    case "TIMED_OUT":
      return {
        label: "Timed Out",
        badgeClass: "bg-orange-950/40 text-orange-300 border-orange-800/60",
        dotClass: "bg-orange-400",
        isAnimated: false,
      };
    default:
      return {
        label: status,
        badgeClass: "bg-slate-800 text-slate-300 border-slate-700",
        dotClass: "bg-slate-400",
        isAnimated: false,
      };
  }
}

export function getDatasetStatusBadge(status: DatasetStatus): StatusBadgeConfig {
  switch (status) {
    case "UPLOADING":
      return {
        label: "Uploading",
        badgeClass: "bg-blue-950/40 text-blue-300 border-blue-800/60",
        dotClass: "bg-blue-400",
        isAnimated: true,
      };
    case "PROFILING":
      return {
        label: "Profiling",
        badgeClass: "bg-amber-950/40 text-amber-300 border-amber-800/60",
        dotClass: "bg-amber-400",
        isAnimated: true,
      };
    case "READY":
      return {
        label: "Ready",
        badgeClass: "bg-emerald-950/40 text-emerald-300 border-emerald-800/60",
        dotClass: "bg-emerald-400",
        isAnimated: false,
      };
    case "INVALID":
      return {
        label: "Invalid",
        badgeClass: "bg-rose-950/40 text-rose-300 border-rose-800/60",
        dotClass: "bg-rose-400",
        isAnimated: false,
      };
    default:
      return {
        label: status,
        badgeClass: "bg-slate-800 text-slate-300 border-slate-700",
        dotClass: "bg-slate-400",
        isAnimated: false,
      };
  }
}

export function getStageStepIndex(stage: string): number {
  const normalized = stage.toLowerCase();
  if (normalized.includes("queued")) return 0;
  if (normalized.includes("provision") || normalized.includes("boot")) return 1;
  if (normalized.includes("preprocess")) return 2;
  if (normalized.includes("train") || normalized.includes("fitting")) return 3;
  if (normalized.includes("eval") || normalized.includes("explain")) return 4;
  if (normalized.includes("upload") || normalized.includes("artifact")) return 5;
  if (normalized.includes("done") || normalized.includes("succeed")) return 6;
  return 0;
}
