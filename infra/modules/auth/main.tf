data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
}

# ──────────────────────────────────────────────
# Cognito User Pool
# ──────────────────────────────────────────────
resource "aws_cognito_user_pool" "pool" {
  name                     = "cloudtrain-${var.env}-users"
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length                   = 10
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = true
    temporary_password_validity_days = 7
  }

  mfa_configuration = "OFF"

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  dynamic "lambda_config" {
    for_each = var.pre_signup_lambda_arn != "" ? [var.pre_signup_lambda_arn] : []
    content {
      pre_sign_up = lambda_config.value
    }
  }

  tags = {
    Name = "cloudtrain-${var.env}-users"
  }
}

# ──────────────────────────────────────────────
# Cognito SPA App Client (Public Client, No Secret)
# ──────────────────────────────────────────────
resource "aws_cognito_user_pool_client" "client" {
  name         = "cloudtrain-${var.env}-spa-client"
  user_pool_id = aws_cognito_user_pool.pool.id

  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 7

  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }

  prevent_user_existence_errors = "ENABLED"
}
