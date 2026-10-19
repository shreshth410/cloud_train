variable "env" {
  type        = string
  description = "Environment name"
}

variable "artifact_retention_days" {
  type        = number
  description = "Days before training artifacts in S3 expire"
  default     = 30
}

variable "enable_local_cors" {
  type        = bool
  description = "Enable localhost in S3 CORS for local testing"
  default     = false
}

variable "dataset_profiler_arn" {
  type        = string
  description = "ARN of dataset_profiler Lambda for S3 notifications (optional)"
  default     = ""
}
