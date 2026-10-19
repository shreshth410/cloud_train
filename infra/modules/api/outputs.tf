output "api_id" {
  description = "ID of the API Gateway HTTP API"
  value       = aws_apigatewayv2_api.api.id
}

output "api_endpoint" {
  description = "Base URL of the API Gateway HTTP API"
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "api_arn" {
  description = "ARN of the API Gateway HTTP API"
  value       = aws_apigatewayv2_api.api.arn
}
