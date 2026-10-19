variable "env" {
  type        = string
  description = "Environment name"
}

variable "trainer_role_arn" {
  type        = string
  description = "ARN of the trainer EC2 IAM role (optional, for queue policy)"
  default     = ""
}
