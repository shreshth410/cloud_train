variable "region" {
  type        = string
  description = "AWS region for all infrastructure resources"
  default     = "ap-south-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]{1}$", var.region))
    error_message = "Must be a valid AWS region identifier (e.g. ap-south-1, us-east-1)."
  }
}

variable "env" {
  type        = string
  description = "Deployment environment name (prod, dev, staging)"
  default     = "prod"

  validation {
    condition     = contains(["prod", "dev", "staging", "test"], var.env)
    error_message = "Environment must be one of: prod, dev, staging, test."
  }
}

variable "alert_email" {
  type        = string
  description = "Email address for platform alarms and budget threshold alerts"
  default     = ""
}

variable "monthly_budget_usd" {
  type        = number
  description = "Monthly budget cap in USD"
  default     = 10

  validation {
    condition     = var.monthly_budget_usd > 0 && var.monthly_budget_usd <= 100
    error_message = "Monthly budget must be between $1 and $100 for safety guardrails."
  }
}

variable "trainer_image_tag" {
  type        = string
  description = "Tag of the trainer container image in ECR"
  default     = "latest"
}

variable "ecr_repository_url" {
  type        = string
  description = "URL of the ECR repository for trainer image"
  default     = ""
}

variable "instance_type_small" {
  type        = string
  description = "Small EC2 instance type for lightweight training"
  default     = "t3.small"

  validation {
    condition     = contains(["t3.small", "t4g.small", "t3.micro", "t4g.micro"], var.instance_type_small)
    error_message = "instance_type_small must be a small/micro general purpose instance."
  }
}

variable "instance_type_medium" {
  type        = string
  description = "Medium EC2 instance type for heavier training"
  default     = "t3.medium"

  validation {
    condition     = contains(["t3.medium", "t4g.medium", "c6i.large"], var.instance_type_medium)
    error_message = "instance_type_medium must be a medium/large general purpose instance."
  }
}

variable "max_concurrent_instances" {
  type        = number
  description = "Strict concurrency cap on simultaneously running EC2 trainers"
  default     = 2

  validation {
    condition     = var.max_concurrent_instances >= 1 && var.max_concurrent_instances <= 4
    error_message = "Concurrency must be between 1 and 4 to preserve cost guardrails."
  }
}

variable "max_active_jobs_per_user" {
  type        = number
  description = "Maximum active queued/running jobs per user"
  default     = 3
}

variable "max_datasets_per_user" {
  type        = number
  description = "Maximum datasets allowed per user"
  default     = 10
}

variable "max_dataset_bytes" {
  type        = number
  description = "Maximum dataset size in bytes (default 100 MB)"
  default     = 104857600
}

variable "max_runtime_minutes" {
  type        = number
  description = "Maximum training job execution runtime in minutes"
  default     = 60
}

variable "artifact_retention_days" {
  type        = number
  description = "Number of days before S3 artifacts expire"
  default     = 30
}

variable "log_retention_days" {
  type        = number
  description = "Number of days before CloudWatch logs expire"
  default     = 14
}

variable "allowed_email_domains" {
  type        = list(string)
  description = "List of allowed domains for Cognito user registration"
  default     = []
}

variable "allowed_emails" {
  type        = list(string)
  description = "List of explicitly allowed email addresses for Cognito user registration"
  default     = []
}

variable "use_spot" {
  type        = bool
  description = "Launch EC2 trainers on Spot market for cost reduction"
  default     = false
}

variable "enable_rds" {
  type        = bool
  description = "Enable optional RDS PostgreSQL database module (Stretch S5)"
  default     = false
}

variable "enable_local_cors" {
  type        = bool
  description = "Enable localhost origins in CORS headers for local frontend testing"
  default     = false
}
