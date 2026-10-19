output "datasets_table_name" {
  description = "Name of the DynamoDB datasets table"
  value       = aws_dynamodb_table.datasets.name
}

output "datasets_table_arn" {
  description = "ARN of the DynamoDB datasets table"
  value       = aws_dynamodb_table.datasets.arn
}

output "jobs_table_name" {
  description = "Name of the DynamoDB jobs table"
  value       = aws_dynamodb_table.jobs.name
}

output "jobs_table_arn" {
  description = "ARN of the DynamoDB jobs table"
  value       = aws_dynamodb_table.jobs.arn
}
