# ──────────────────────────────────────────────
# API Gateway HTTP API
# ──────────────────────────────────────────────
resource "aws_apigatewayv2_api" "api" {
  name          = "cloudtrain-${var.env}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers = [
      "Content-Type",
      "Authorization",
      "X-Amz-Date",
      "X-Api-Key",
      "X-Amz-Security-Token"
    ]
    allow_methods = ["GET", "POST", "DELETE", "OPTIONS"]
    allow_origins = var.enable_local_cors ? [
      "http://localhost:3000",
      "http://localhost:5173",
      "http://127.0.0.1:4173"
    ] : ["https://*"]
    max_age = 300
  }

  tags = {
    Name = "cloudtrain-${var.env}-api"
  }
}

# ──────────────────────────────────────────────
# Cognito JWT Authorizer
# ──────────────────────────────────────────────
resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.api.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "cognito-jwt-authorizer"

  jwt_configuration {
    audience = [var.user_pool_client_id]
    issuer   = "https://cognito-idp.${var.region}.amazonaws.com/${var.user_pool_id}"
  }
}

# ──────────────────────────────────────────────
# Lambda Integration
# ──────────────────────────────────────────────
resource "aws_apigatewayv2_integration" "api_lambda" {
  api_id           = aws_apigatewayv2_api.api.id
  integration_type = "AWS_PROXY"
  integration_uri  = var.api_lambda_arn

  payload_format_version = "2.0"
}

# ──────────────────────────────────────────────
# Explicit Route Definitions
# ──────────────────────────────────────────────
locals {
  protected_routes = [
    "GET /me",
    "GET /models",
    "GET /datasets",
    "POST /datasets",
    "GET /datasets/{id}",
    "DELETE /datasets/{id}",
    "GET /jobs",
    "POST /jobs",
    "GET /jobs/{id}",
    "POST /jobs/{id}/cancel",
    "DELETE /jobs/{id}",
    "GET /jobs/{id}/results",
    "GET /jobs/{id}/artifacts",
    "GET /jobs/{id}/logs"
  ]
}

resource "aws_apigatewayv2_route" "protected" {
  for_each = toset(local.protected_routes)

  api_id             = aws_apigatewayv2_api.api.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
  authorization_type = "JWT"
}

# Public Health Route (No Auth)
resource "aws_apigatewayv2_route" "health" {
  api_id             = aws_apigatewayv2_api.api.id
  route_key          = "GET /health"
  target             = "integrations/${aws_apigatewayv2_integration.api_lambda.id}"
  authorization_type = "NONE"
}

# ──────────────────────────────────────────────
# Stage: $default with access logging & throttling
# ──────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "api_access_logs" {
  name              = "/aws/apigateway/cloudtrain-${var.env}"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 50
    throttling_rate_limit  = 20
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access_logs.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
    })
  }
}

resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.api_lambda_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
