output "cloudfront_url" {
  description = "Public URL of the CloudFront distribution serving the SPA"
  value       = module.frontend.cloudfront_url
}

output "api_url" {
  description = "Base URL of the API Gateway HTTP API"
  value       = module.api.api_endpoint
}

output "user_pool_id" {
  description = "ID of the Cognito User Pool"
  value       = module.auth.user_pool_id
}

output "user_pool_client_id" {
  description = "Client ID of the Cognito SPA User Pool Client"
  value       = module.auth.user_pool_client_id
}

output "data_bucket" {
  description = "Name of the S3 data bucket for datasets and artifacts"
  value       = module.storage.data_bucket_id
}

output "web_bucket" {
  description = "Name of the S3 web bucket hosting frontend build"
  value       = module.storage.web_bucket_id
}

output "jobs_queue_url" {
  description = "URL of the SQS jobs queue"
  value       = module.messaging.jobs_queue_url
}

output "status_queue_url" {
  description = "URL of the SQS status queue"
  value       = module.messaging.status_queue_url
}

output "jobs_dlq_url" {
  description = "URL of the SQS jobs dead-letter queue"
  value       = module.messaging.jobs_dlq_url
}

output "trainer_log_group" {
  description = "Name of the CloudWatch Log Group for training container logs"
  value       = module.compute.trainer_log_group_name
}

output "launch_template_id" {
  description = "ID of the EC2 Launch Template for training instances"
  value       = module.compute.launch_template_id
}

output "cloudfront_distribution_id" {
  description = "ID of the CloudFront distribution (for cache invalidations)"
  value       = module.frontend.cloudfront_distribution_id
}
