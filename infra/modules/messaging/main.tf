# ──────────────────────────────────────────────
# Jobs Dead Letter Queue
# ──────────────────────────────────────────────
resource "aws_sqs_queue" "jobs_dlq" {
  name                      = "cloudtrain-${var.env}-jobs-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true

  tags = {
    Name = "cloudtrain-${var.env}-jobs-dlq"
  }
}

# ──────────────────────────────────────────────
# Main Jobs Queue
# ──────────────────────────────────────────────
resource "aws_sqs_queue" "jobs" {
  name                       = "cloudtrain-${var.env}-jobs"
  visibility_timeout_seconds = 600
  message_retention_seconds  = 345600 # 4 days
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.jobs_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "cloudtrain-${var.env}-jobs"
  }
}

# ──────────────────────────────────────────────
# Status Dead Letter Queue
# ──────────────────────────────────────────────
resource "aws_sqs_queue" "status_dlq" {
  name                      = "cloudtrain-${var.env}-status-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true

  tags = {
    Name = "cloudtrain-${var.env}-status-dlq"
  }
}

# ──────────────────────────────────────────────
# Main Status Queue
# ──────────────────────────────────────────────
resource "aws_sqs_queue" "status" {
  name                       = "cloudtrain-${var.env}-status"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 345600 # 4 days
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.status_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name = "cloudtrain-${var.env}-status"
  }
}

# ──────────────────────────────────────────────
# Queue Policies (Enforce TLS + Status SendMessage)
# ──────────────────────────────────────────────
resource "aws_sqs_queue_policy" "jobs_tls" {
  queue_url = aws_sqs_queue.jobs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "EnforceTLSRequestsOnly"
        Effect    = "Deny"
        Principal = "*"
        Action    = "sqs:*"
        Resource  = aws_sqs_queue.jobs.arn
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })
}

resource "aws_sqs_queue_policy" "status_policy" {
  queue_url = aws_sqs_queue.status.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [
        {
          Sid       = "EnforceTLSRequestsOnly"
          Effect    = "Deny"
          Principal = "*"
          Action    = "sqs:*"
          Resource  = aws_sqs_queue.status.arn
          Condition = {
            Bool = {
              "aws:SecureTransport" = "false"
            }
          }
        }
      ],
      var.trainer_role_arn != "" ? [
        {
          Sid    = "AllowTrainerSendMessage"
          Effect = "Allow"
          Principal = {
            AWS = var.trainer_role_arn
          }
          Action   = "sqs:SendMessage"
          Resource = aws_sqs_queue.status.arn
        }
      ] : []
    )
  })
}
