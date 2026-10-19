variable "region" {
  type        = string
  description = "AWS region for bootstrap resources"
  default     = "ap-south-1"
}

variable "github_repo" {
  type        = string
  description = "GitHub repository in the format owner/repo (e.g., student/cloudtrain)"
}

variable "env" {
  type        = string
  description = "Deployment environment name"
  default     = "prod"
}
