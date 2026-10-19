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
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
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
  return request<UserQuota>("/me");
}

export async function fetchModels(): Promise<ModelMetadata[]> {
  const res = await request<{ models: ModelMetadata[] }>("/models");
  return res.models || [];
}

export async function fetchDatasets(): Promise<Dataset[]> {
  const res = await request<{ datasets: Dataset[] }>("/datasets");
  return res.datasets || [];
}

export async function fetchDataset(id: string): Promise<Dataset> {
  return request<Dataset>(`/datasets/${id}`);
}

export async function deleteDataset(id: string): Promise<void> {
  return request<void>(`/datasets/${id}`, { method: "DELETE" });
}

export interface PresignedPost {
  url: string;
  fields: Record<string, string>;
  dataset_id: string;
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

    Object.entries(presigned.fields).forEach(([k, v]) => {
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
    xhr.open("POST", presigned.url);
    xhr.send(formData);
  });
}

export async function fetchJobs(status?: string): Promise<Job[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await request<{ jobs: Job[] }>(`/jobs${query}`);
  return res.jobs || [];
}

export async function fetchJob(id: string): Promise<Job> {
  return request<Job>(`/jobs/${id}`);
}

export async function createJob(config: JobConfig): Promise<{ job_id: string; status: string }> {
  return request<{ job_id: string; status: string }>("/jobs", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export async function cancelJob(id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/jobs/${id}/cancel`, { method: "POST" });
}

export async function deleteJob(id: string): Promise<void> {
  return request<void>(`/jobs/${id}`, { method: "DELETE" });
}

export async function fetchJobResults(id: string): Promise<JobResults> {
  return request<JobResults>(`/jobs/${id}/results`);
}

export async function fetchJobArtifacts(id: string): Promise<PresignedArtifacts> {
  return request<PresignedArtifacts>(`/jobs/${id}/artifacts`);
}

export async function fetchJobLogs(id: string): Promise<{ logs: string; is_live: boolean }> {
  return request<{ logs: string; is_live: boolean }>(`/jobs/${id}/logs`);
}
