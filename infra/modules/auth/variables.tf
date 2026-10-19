variable "env" {
  type        = string
  description = "Environment name"
}

variable "pre_signup_lambda_arn" {
  type        = string
  description = "ARN of the pre_signup Lambda function for allow-list enforcement"
  default     = ""
}
