import React from "react";
import { JobStatus, DatasetStatus } from "@/types";
import { getJobStatusBadge, getDatasetStatusBadge } from "@/utils/formatters";

interface JobStatusBadgeProps {
  status: JobStatus;
  size?: "sm" | "md";
}

export const JobStatusBadge: React.FC<JobStatusBadgeProps> = ({ status, size = "md" }) => {
  const badge = getJobStatusBadge(status);
  const sizeClasses = size === "sm" ? "text-xs px-2 py-0.5" : "text-xs px-2.5 py-1";

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium rounded-full border ${badge.badgeClass} ${sizeClasses}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${badge.dotClass} ${
          badge.isAnimated ? "animate-pulse" : ""
        }`}
      />
      {badge.label}
    </span>
  );
};

interface DatasetStatusBadgeProps {
  status: DatasetStatus;
  size?: "sm" | "md";
}

export const DatasetStatusBadge: React.FC<DatasetStatusBadgeProps> = ({
  status,
  size = "md",
}) => {
  const badge = getDatasetStatusBadge(status);
  const sizeClasses = size === "sm" ? "text-xs px-2 py-0.5" : "text-xs px-2.5 py-1";

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium rounded-full border ${badge.badgeClass} ${sizeClasses}`}
    >
      <span
        className={`w-1.5 h-1.5 rounded-full ${badge.dotClass} ${
          badge.isAnimated ? "animate-pulse" : ""
        }`}
      />
      {badge.label}
    </span>
  );
};
