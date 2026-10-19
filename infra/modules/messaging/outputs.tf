output "jobs_queue_url" {
  description = "URL of the jobs SQS queue"
  value       = aws_sqs_queue.jobs.id
}

output "jobs_queue_arn" {
  description = "ARN of the jobs SQS queue"
  value       = aws_sqs_queue.jobs.arn
}

output "jobs_dlq_url" {
  description = "URL of the jobs DLQ"
  value       = aws_sqs_queue.jobs_dlq.id
}

output "jobs_dlq_arn" {
  description = "ARN of the jobs DLQ"
  value       = aws_sqs_queue.jobs_dlq.arn
}

output "status_queue_url" {
  description = "URL of the status SQS queue"
  value       = aws_sqs_queue.status.id
}

output "status_queue_arn" {
  description = "ARN of the status SQS queue"
  value       = aws_sqs_queue.status.arn
}

output "status_dlq_url" {
  description = "URL of the status DLQ"
  value       = aws_sqs_queue.status_dlq.id
}

output "status_dlq_arn" {
  description = "ARN of the status DLQ"
  value       = aws_sqs_queue.status_dlq.arn
}
