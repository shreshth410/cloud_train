output "data_bucket_id" {
  description = "Name of the S3 data bucket"
  value       = aws_s3_bucket.data.id
}

output "data_bucket_arn" {
  description = "ARN of the S3 data bucket"
  value       = aws_s3_bucket.data.arn
}

output "web_bucket_id" {
  description = "Name of the S3 web bucket"
  value       = aws_s3_bucket.web.id
}

output "web_bucket_arn" {
  description = "ARN of the S3 web bucket"
  value       = aws_s3_bucket.web.arn
}

output "web_bucket_regional_domain_name" {
  description = "Regional domain name of the S3 web bucket for CloudFront origin"
  value       = aws_s3_bucket.web.bucket_regional_domain_name
}
