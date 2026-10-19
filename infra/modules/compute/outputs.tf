output "launch_template_id" {
  description = "ID of the EC2 Launch Template"
  value       = aws_launch_template.trainer.id
}

output "launch_template_arn" {
  description = "ARN of the EC2 Launch Template"
  value       = aws_launch_template.trainer.arn
}

output "launch_template_latest_version" {
  description = "Latest version number of the Launch Template"
  value       = aws_launch_template.trainer.latest_version
}

output "trainer_role_arn" {
  description = "ARN of the trainer IAM role"
  value       = aws_iam_role.trainer.arn
}

output "trainer_log_group_name" {
  description = "Name of the training CloudWatch Log Group"
  value       = aws_cloudwatch_log_group.training.name
}

output "trainer_log_group_arn" {
  description = "ARN of the training CloudWatch Log Group"
  value       = aws_cloudwatch_log_group.training.arn
}
