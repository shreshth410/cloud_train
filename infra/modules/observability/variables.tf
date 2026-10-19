variable "env" {
  type        = string
  description = "Environment name"
}

variable "region" {
  type        = string
  description = "AWS region"
}

variable "alert_email" {
  type        = string
  description = "Email address for SNS alert notifications and budget threshold alerts"
}

variable "monthly_budget_usd" {
  type        = number
  description = "Monthly budget limit in USD"
  default     = 10
}

variable "jobs_queue_name" {
  type        = string
  description = "Name of the jobs SQS queue"
}

variable "jobs_dlq_name" {
  type        = string
  description = "Name of the jobs DLQ"
}

variable "status_dlq_name" {
  type        = string
  description = "Name of the status DLQ"
}

variable "api_id" {
  type        = string
  description = "ID of the API Gateway HTTP API"
}
