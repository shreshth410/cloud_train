variable "env" {
  type        = string
  description = "Environment name"
}

variable "region" {
  type        = string
  description = "AWS region"
}

variable "data_bucket_name" {
  type        = string
  description = "Name of the S3 data bucket"
}

variable "data_bucket_arn" {
  type        = string
  description = "ARN of the S3 data bucket"
}

variable "status_queue_arn" {
  type        = string
  description = "ARN of the SQS status queue"
}

variable "trainer_security_group_id" {
  type        = string
  description = "Security Group ID for training instances"
}

variable "instance_type_small" {
  type        = string
  description = "Default small EC2 instance type"
  default     = "t3.small"
}

variable "instance_type_medium" {
  type        = string
  description = "Medium EC2 instance type"
  default     = "t3.medium"
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch log retention in days"
  default     = 14
}

variable "use_spot" {
  type        = bool
  description = "Use EC2 Spot instances for training (cost optimization)"
  default     = false
}
