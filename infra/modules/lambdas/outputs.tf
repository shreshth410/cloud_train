output "api_lambda_arn" {
  description = "ARN of the API Lambda function"
  value       = aws_lambda_function.api.arn
}

output "api_lambda_name" {
  description = "Name of the API Lambda function"
  value       = aws_lambda_function.api.function_name
}

output "dataset_profiler_lambda_arn" {
  description = "ARN of the dataset profiler Lambda function"
  value       = aws_lambda_function.dataset_profiler.arn
}

output "pre_signup_lambda_arn" {
  description = "ARN of the pre-signup Lambda function"
  value       = aws_lambda_function.pre_signup.arn
}

output "watchdog_lambda_arn" {
  description = "ARN of the watchdog Lambda function"
  value       = aws_lambda_function.watchdog.arn
}
