variable "env" {
  type        = string
  description = "Environment name"
}

variable "region" {
  type        = string
  description = "AWS region"
}

variable "web_bucket_id" {
  type        = string
  description = "Name of the S3 web bucket"
}

variable "web_bucket_arn" {
  type        = string
  description = "ARN of the S3 web bucket"
}

variable "web_bucket_regional_domain_name" {
  type        = string
  description = "Regional domain name of the S3 web bucket"
}

variable "api_endpoint" {
  type        = string
  description = "API Gateway endpoint URL"
}

variable "user_pool_id" {
  type        = string
  description = "Cognito User Pool ID"
}

variable "user_pool_client_id" {
  type        = string
  description = "Cognito User Pool Client ID"
}
