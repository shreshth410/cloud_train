variable "env" {
  type        = string
  description = "Environment name"
}

variable "region" {
  type        = string
  description = "AWS region"
}

variable "data_bucket_id" {
  type        = string
  description = "Name of the S3 data bucket"
}

variable "data_bucket_arn" {
  type        = string
  description = "ARN of the S3 data bucket"
}

variable "jobs_table_name" {
  type        = string
  description = "Name of the DynamoDB jobs table"
}

variable "jobs_table_arn" {
  type        = string
  description = "ARN of the DynamoDB jobs table"
}

variable "datasets_table_name" {
  type        = string
  description = "Name of the DynamoDB datasets table"
}

variable "datasets_table_arn" {
  type        = string
  description = "ARN of the DynamoDB datasets table"
}

variable "jobs_queue_arn" {
  type        = string
  description = "ARN of the jobs SQS queue"
}

variable "jobs_queue_url" {
  type        = string
  description = "URL of the jobs SQS queue"
}

variable "jobs_dlq_arn" {
  type        = string
  description = "ARN of the jobs DLQ"
}

variable "status_queue_arn" {
  type        = string
  description = "ARN of the status SQS queue"
}

variable "status_queue_url" {
  type        = string
  description = "URL of the status SQS queue"
}

variable "launch_template_id" {
  type        = string
  description = "Launch Template ID for EC2 trainer"
}

variable "subnet_ids" {
  type        = list(string)
  description = "List of public subnet IDs for launching training instances"
}

variable "trainer_security_group_id" {
  type        = string
  description = "Security Group ID for training instances"
}

variable "trainer_role_arn" {
  type        = string
  description = "ARN of the trainer EC2 IAM role (for iam:PassRole)"
}

variable "ecr_repository_url" {
  type        = string
  description = "URL of the ECR trainer repository"
  default     = ""
}

variable "trainer_image_tag" {
  type        = string
  description = "Trainer container image tag"
  default     = "latest"
}

variable "max_concurrent_instances" {
  type        = number
  description = "Maximum concurrent training instances allowed"
  default     = 2
}

variable "max_runtime_minutes" {
  type        = number
  description = "Maximum execution runtime in minutes before watchdog kills instance"
  default     = 60
}

variable "allowed_email_domains" {
  type        = list(string)
  description = "Allowed email domains for registration"
  default     = []
}

variable "allowed_emails" {
  type        = list(string)
  description = "Allowed specific email addresses for registration"
  default     = []
}

variable "log_retention_days" {
  type        = number
  description = "Log retention in days"
  default     = 14
}
