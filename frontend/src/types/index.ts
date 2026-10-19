export type JobStatus =
  | "QUEUED"
  | "PROVISIONING"
  | "RUNNING"
  | "UPLOADING"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED"
  | "TIMED_OUT";

export type DatasetStatus = "UPLOADING" | "PROFILING" | "READY" | "INVALID";

export type TaskType = "classification" | "regression";

export type ComputeSize = "small" | "medium";

export interface UserQuota {
  user_id: string;
  datasets: {
    count: number;
    max: number;
  };
  active_jobs: {
    count: number;
    max: number;
  };
  total_jobs: {
    count: number;
  };
}

export interface ColumnProfile {
  name: string;
  dtype: string;
  inferred_type: "numeric" | "categorical" | "boolean" | "datetime" | "id_like" | "constant" | "text";
  missing_count: number;
  missing_pct: number;
  unique_count: number;
  sample_values?: (string | number | boolean | null)[];
  stats?: {
    mean?: number;
    std?: number;
    min?: number;
    max?: number;
    q25?: number;
    median?: number;
    q75?: number;
  };
}

export interface DatasetWarning {
  column?: string;
  type: string;
  message: string;
  severity: "info" | "warning" | "error";
}

export interface DatasetProfile {
  row_count: number;
  column_count: number;
  columns: ColumnProfile[];
  preview: Record<string, any>[];
  warnings: DatasetWarning[];
  delimiter?: string;
  encoding?: string;
  filesize_bytes?: number;
}

export interface Dataset {
  dataset_id: string;
  user_id: string;
  name: string;
  filename: string;
  size_bytes: number;
  status: DatasetStatus;
  profile?: DatasetProfile;
  error?: {
    code: string;
    message: string;
  };
  created_at: string;
  updated_at: string;
}

export interface HyperparameterDef {
  type: "int" | "float" | "str" | "bool";
  default: any;
  min?: number;
  max?: number;
  step?: number;
  options?: string[];
  nullable?: boolean;
  description: string;
}

export interface ModelMetadata {
  id: string;
  name: string;
  task: TaskType[];
  description: string;
  needs_scaling: boolean;
  recommended?: boolean;
  hyperparameters: Record<string, HyperparameterDef>;
}

export interface JobConfig {
  name?: string;
  dataset_id: string;
  target_column: string;
  task?: TaskType;
  feature_columns?: string[];
  model: {
    id: string;
    hyperparameters?: Record<string, any>;
  };
  compute_size?: ComputeSize;
  preprocessing?: {
    numeric_impute?: "mean" | "median" | "constant";
    scale_numeric?: boolean;
    categorical_impute?: "most_frequent" | "constant";
    max_categories?: number;
    drop_id_like?: boolean;
  };
  split?: {
    test_size?: number;
    stratify?: boolean;
    random_state?: number;
  };
  cross_validation?: {
    folds?: number;
  };
}

export interface Job {
  job_id: string;
  user_id: string;
  name: string;
  dataset_id: string;
  status: JobStatus;
  stage: string;
  progress: number;
  compute_size: ComputeSize;
  config: JobConfig;
  error?: {
    code: string;
    message: string;
    suggested_fix?: string;
  };
  created_at: string;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  metrics_summary?: Record<string, number>;
}

export interface ConfusionMatrix {
  labels: string[];
  matrix: number[][];
}

export interface ClassReport {
  precision: number;
  recall: number;
  f1: number;
  support: number;
}

export interface JobResults {
  job_id: string;
  task: TaskType;
  model: {
    id: string;
    hyperparameters: Record<string, any>;
  };
  rows: {
    train: number;
    test: number;
  };
  n_features_after_encoding: number;
  classes?: string[];
  metrics: Record<string, any>;
  baseline?: Record<string, any>;
  confusion_matrix?: ConfusionMatrix;
  per_class?: Record<string, ClassReport>;
  roc_curve?: {
    fpr: number[];
    tpr: number[];
  };
  predictions_sample?: {
    actual: number;
    predicted: number;
  }[];
  residual_histogram?: {
    bins: number[];
    counts: number[];
  };
  cv?: {
    folds: number;
    [key: string]: any;
  };
  timing?: {
    fit_seconds: number;
    total_seconds: number;
  };
  library_versions?: Record<string, string>;
  feature_importance?: {
    features: { feature: string; importance: number }[];
    aggregated_by_original_column?: { feature: string; importance: number }[];
  };
  preprocessing_report?: {
    excluded_columns?: { column: string; reason: string }[];
    engineered_features?: string[];
  };
  model_card_markdown?: string;
}

export interface PresignedArtifacts {
  model_joblib?: string;
  metrics_json?: string;
  model_card_md?: string;
  predict_example_py?: string;
  requirements_txt?: string;
  logs_txt?: string;
  feature_importance_json?: string;
  preprocessing_report_json?: string;
}

export interface RuntimeConfig {
  api_url: string;
  region: string;
  user_pool_id: string;
  user_pool_client_id: string;
}
