variable "env" {
  type        = string
  description = "Environment name"
}

variable "region" {
  type        = string
  description = "AWS region"
}

variable "api_lambda_arn" {
  type        = string
  description = "ARN of the api Lambda function"
}

variable "api_lambda_name" {
  type        = string
  description = "Name of the api Lambda function"
}

variable "user_pool_id" {
  type        = string
  description = "ID of the Cognito User Pool"
}

variable "user_pool_client_id" {
  type        = string
  description = "Client ID of the Cognito User Pool Client"
}

variable "enable_local_cors" {
  type        = bool
  description = "Enable localhost origins for CORS"
  default     = false
}

variable "log_retention_days" {
  type        = number
  description = "Log retention in days"
  default     = 14
}
