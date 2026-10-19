import { describe, it, expect } from "vitest";
import {
  formatBytes,
  formatDuration,
  formatDate,
  getJobStatusBadge,
  getDatasetStatusBadge,
} from "@/utils/formatters";

describe("Formatting Helpers", () => {
  it("formats byte sizes accurately", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(1024 * 1024 * 5.5)).toBe("5.5 MB");
    expect(formatBytes(1024 * 1024 * 1024 * 2)).toBe("2 GB");
  });

  it("formats execution durations across seconds, minutes, and hours", () => {
    expect(formatDuration(undefined)).toBe("—");
    expect(formatDuration(42)).toBe("42s");
    expect(formatDuration(125)).toBe("2m 5s");
    expect(formatDuration(3665)).toBe("1h 1m");
  });

  it("formats ISO timestamps gracefully", () => {
    expect(formatDate(undefined)).toBe("—");
    const formatted = formatDate("2026-10-19T12:00:00Z");
    expect(formatted).toBeTruthy();
    expect(formatted).not.toBe("—");
  });

  it("maps job statuses to correct color schemes and animation states", () => {
    const runningBadge = getJobStatusBadge("RUNNING");
    expect(runningBadge.label).toBe("Running");
    expect(runningBadge.isAnimated).toBe(true);

    const succeededBadge = getJobStatusBadge("SUCCEEDED");
    expect(succeededBadge.label).toBe("Succeeded");
    expect(succeededBadge.isAnimated).toBe(false);

    const queuedBadge = getJobStatusBadge("QUEUED");
    expect(queuedBadge.label).toBe("Queued");

    const failedBadge = getJobStatusBadge("FAILED");
    expect(failedBadge.label).toBe("Failed");
  });

  it("maps dataset statuses to badge configs", () => {
    const profilingBadge = getDatasetStatusBadge("PROFILING");
    expect(profilingBadge.label).toBe("Profiling");
    expect(profilingBadge.isAnimated).toBe(true);

    const readyBadge = getDatasetStatusBadge("READY");
    expect(readyBadge.label).toBe("Ready");
    expect(readyBadge.isAnimated).toBe(false);
  });
});
