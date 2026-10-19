output "state_bucket" {
  description = "Name of the S3 bucket for Terraform remote state"
  value       = aws_s3_bucket.tfstate.id
}

output "ecr_repository_url" {
  description = "URL of the ECR repository for the training container"
  value       = aws_ecr_repository.trainer.repository_url
}

output "gha_plan_role_arn" {
  description = "ARN of the IAM role for GitHub Actions PR terraform plan"
  value       = aws_iam_role.gha_plan.arn
}

output "gha_deploy_role_arn" {
  description = "ARN of the IAM role for GitHub Actions prod deployment"
  value       = aws_iam_role.gha_deploy.arn
}
