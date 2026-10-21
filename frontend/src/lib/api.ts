import {
  Dataset,
  Job,
  JobConfig,
  JobResults,
  ModelMetadata,
  PresignedArtifacts,
  RuntimeConfig,
  UserQuota,
} from "@/types";

let cachedConfig: RuntimeConfig | null = null;

export async function getRuntimeConfig(): Promise<RuntimeConfig> {
  if (cachedConfig) return cachedConfig;
  try {
    const res = await fetch("/config.json");
    if (!res.ok) throw new Error("Failed to load /config.json");
    cachedConfig = await res.json();
    return cachedConfig!;
  } catch (err) {
    console.warn("Using fallback runtime config", err);
    cachedConfig = {
      api_url: "http://localhost:8000",
      region: "ap-south-1",
      user_pool_id: "ap-south-1_LOCAL",
      user_pool_client_id: "local_client_id",
    };
    return cachedConfig!;
  }
}

export function getAuthToken(): string | null {
  return localStorage.getItem("cloudtrain_token") || "mock-token";
}

export function setAuthToken(token: string | null, email?: string, sub?: string) {
  if (token) {
    localStorage.setItem("cloudtrain_token", token);
    if (email) localStorage.setItem("cloudtrain_user_email", email);
    if (sub) localStorage.setItem("cloudtrain_user_id", sub);
  } else {
    localStorage.removeItem("cloudtrain_token");
    localStorage.removeItem("cloudtrain_user_email");
    localStorage.removeItem("cloudtrain_user_id");
  }
}

export function getStoredUser(): { email: string; userId: string } {
  return {
    email: localStorage.getItem("cloudtrain_user_email") || "local-engineer@cloudtrain.dev",
    userId: localStorage.getItem("cloudtrain_user_id") || "local-user",
  };
}

export class ApiError extends Error {
  status: number;
  code?: string;
  fields?: { path: string; message: string }[];
  details?: any;

  constructor(status: number, message: string, code?: string, fields?: any[], details?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.details = details;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const config = await getRuntimeConfig();
  const url = `${config.api_url.replace(/\/$/, "")}${path}`;

  const headers = new Headers(options.headers);
  const token = getAuthToken();
  const user = getStoredUser();

  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (user.userId && !headers.has("x-user-sub")) {
    headers.set("x-user-sub", user.userId);
  }
  if (user.email && !headers.has("x-user-email")) {
    headers.set("x-user-email", user.email);
  }
  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 204) {
    return {} as T;
  }

  let body: any;
  const contentType = response.headers.get("content-type");
  if (contentType && contentType.includes("application/json")) {
    body = await response.json();
  } else {
    body = await response.text();
  }

  if (!response.ok) {
    const errorObj = typeof body === "object" ? body.error || body : { message: body };
    throw new ApiError(
      response.status,
      errorObj.message || `API error (${response.status})`,
      errorObj.code,
      errorObj.fields || errorObj.details?.fields,
      errorObj
    );
  }

  return body as T;
}

// ──────────────────────────────────────────────
// API Service Methods
// ──────────────────────────────────────────────

export async function fetchQuotas(): Promise<UserQuota> {
  const result = await request<{ user_id: string; quotas: { datasets_used: number; datasets_max: number; active_jobs: number; active_jobs_max: number } }>("/me");
  const jobs = await fetchJobs();
  return { user_id: result.user_id, datasets: { count: result.quotas.datasets_used, max: result.quotas.datasets_max }, active_jobs: { count: result.quotas.active_jobs, max: result.quotas.active_jobs_max }, total_jobs: { count: jobs.length } };
}

export async function fetchModels(): Promise<ModelMetadata[]> {
  const res = await request<{ models: any[] }>("/models");
  return res.models.map(model => ({
    ...model, name: model.display_name, task: model.tasks,
    hyperparameters: Object.fromEntries(model.hyperparameters.map((param: any) => [param.name, { ...param, type: param.type === "enum" ? "str" : param.type, description: param.help || param.label }]))
  }));
}

// Adapt the documented backend profile to the view model used by the wizard and tables.
function normalizeDataset(dataset: any): Dataset {
  const profile = dataset.profile;
  return {
    ...dataset, filename: dataset.filename || dataset.name,
    error: dataset.errors?.length ? { code: "INVALID_DATASET", message: dataset.errors.join(" ") } : dataset.error,
    profile: profile ? {
      ...profile,
      columns: profile.columns.map((col: any) => ({ ...col, inferred_type: col.dtype, missing_pct: col.missing_pct / 100 })),
      warnings: (profile.warnings || []).map((message: string) => ({ type: "profile", severity: "warning", message })),
      preview: (profile.preview_rows || []).map((row: unknown[]) => Object.fromEntries(profile.columns.map((col: any, index: number) => [col.name, row[index]])))
    } : undefined
  };
}

export async function fetchDatasets(): Promise<Dataset[]> {
  const res = await request<{ datasets?: Dataset[]; items?: Dataset[] }>("/datasets");
  return (res.datasets || res.items || []).map(normalizeDataset);
}

export async function fetchDataset(id: string): Promise<Dataset> {
  return normalizeDataset(await request<Dataset>(`/datasets/${id}`));
}

export async function deleteDataset(id: string): Promise<void> {
  return request<void>(`/datasets/${id}`, { method: "DELETE" });
}

export interface PresignedPost {
  url?: string;
  fields?: Record<string, string>;
  dataset_id: string;
  upload?: {
    url: string;
    fields: Record<string, string>;
  };
  expires_in?: number;
}

export async function initiateDatasetUpload(payload: {
  name: string;
  filename: string;
  size_bytes: number;
}): Promise<PresignedPost> {
  return request<PresignedPost>("/datasets", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function uploadFileToPresignedPost(
  presigned: PresignedPost,
  file: File,
  onProgress?: (pct: number) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    const uploadUrl = presigned.url || presigned.upload?.url;
    const uploadFields = presigned.fields || presigned.upload?.fields || {};

    if (!uploadUrl) {
      reject(new Error("Missing presigned S3 upload URL."));
      return;
    }

    Object.entries(uploadFields).forEach(([k, v]) => {
      formData.append(k, v);
    });
    formData.append("file", file);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        const pct = Math.round((event.loaded / event.total) * 100);
        onProgress(pct);
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`S3 upload failed with status ${xhr.status}: ${xhr.responseText}`));
      }
    };

    xhr.onerror = () => reject(new Error("Network error during S3 direct upload"));
    xhr.open("POST", uploadUrl);
    xhr.send(formData);
  });
}

export async function fetchJobs(status?: string): Promise<Job[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await request<{ jobs?: Job[]; items?: Job[] }>(`/jobs${query}`);
  return res.jobs || res.items || [];
}

export async function fetchJob(id: string): Promise<Job> {
  return request<Job>(`/jobs/${id}`);
}

export async function createJob(config: JobConfig): Promise<{ job_id: string; status: string }> {
  const { compute_size, ...rest } = config;
  return request<{ job_id: string; status: string }>("/jobs", {
    method: "POST",
    body: JSON.stringify({ ...rest, compute: { size: compute_size || "small" } }),
  });
}

export async function cancelJob(id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/jobs/${id}/cancel`, { method: "POST" });
}

export async function deleteJob(id: string): Promise<void> {
  return request<void>(`/jobs/${id}`, { method: "DELETE" });
}

export async function fetchJobResults(id: string): Promise<JobResults> {
  const result = await request<{ metrics: any; feature_importance: any }>(`/jobs/${id}/results`);
  const metrics = result.metrics;
  return {
    ...metrics, job_id: id, metrics,
    rows: { train: metrics.train_rows, test: metrics.test_rows },
    timing: { fit_seconds: metrics.fit_seconds, total_seconds: metrics.total_seconds ?? metrics.fit_seconds },
    confusion_matrix: metrics.confusion_matrix ? { ...metrics.confusion_matrix, labels: metrics.confusion_matrix.classes } : undefined,
    feature_importance: {
      features: result.feature_importance.top_features || [],
      aggregated_by_original_column: (result.feature_importance.aggregated_by_original_column || []).map((item: any) => ({ ...item, feature: item.column }))
    }
  };
}

export async function fetchJobArtifacts(id: string): Promise<PresignedArtifacts> {
  const result = await request<{ files: { name: string; url: string }[] }>(`/jobs/${id}/artifacts`);
  return Object.fromEntries(result.files.map(file => [file.name.replaceAll(".", "_"), file.url]));
}

export async function fetchJobLogs(id: string): Promise<{ logs: string; is_live: boolean }> {
  const result = await request<{ lines: { text: string }[]; source: string }>(`/jobs/${id}/logs`);
  return { logs: result.lines.map(line => line.text).join("\n"), is_live: result.source === "cloudwatch" };
}
