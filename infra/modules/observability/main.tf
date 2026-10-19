# ──────────────────────────────────────────────
# SNS Alert Topic & Email Subscription
# ──────────────────────────────────────────────
resource "aws_sns_topic" "alerts" {
  name = "cloudtrain-${var.env}-alerts"

  tags = {
    Name = "cloudtrain-${var.env}-alerts"
  }
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ──────────────────────────────────────────────
# CloudWatch Alarms
# ──────────────────────────────────────────────

# 1. Jobs DLQ Messages Visible > 0
resource "aws_cloudwatch_metric_alarm" "jobs_dlq" {
  alarm_name          = "cloudtrain-${var.env}-jobs-dlq-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "Alarm when jobs DLQ receives poison or failed messages"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    QueueName = var.jobs_dlq_name
  }
}

# 2. Status DLQ Messages Visible > 0
resource "aws_cloudwatch_metric_alarm" "status_dlq" {
  alarm_name          = "cloudtrain-${var.env}-status-dlq-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "Alarm when status DLQ receives unparseable status events"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    QueueName = var.status_dlq_name
  }
}

# 3. Jobs Queue Oldest Message Age > 900s (Stuck waiting in queue)
resource "aws_cloudwatch_metric_alarm" "jobs_queue_age" {
  alarm_name          = "cloudtrain-${var.env}-jobs-queue-age-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 900
  alarm_description   = "Alarm when training jobs wait > 15 minutes in queue without being launched"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    QueueName = var.jobs_queue_name
  }
}

# 4. API Gateway 5xx Errors >= 5 in 5m
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "cloudtrain-${var.env}-api-5xx-alarm"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "5XXError"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Alarm when API Gateway returns 5 or more 5xx errors in 5 minutes"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimensions = {
    ApiId = var.api_id
  }
}

# ──────────────────────────────────────────────
# AWS Budget Guardrail ($10 Budget with Alerts)
# ──────────────────────────────────────────────
resource "aws_budgets_budget" "monthly" {
  name              = "cloudtrain-${var.env}-monthly-budget"
  budget_type       = "COST"
  limit_amount      = tostring(var.monthly_budget_usd)
  limit_unit        = "USD"
  time_unit         = "MONTHLY"
  time_period_start = "2026-01-01_00:00"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alert_email != "" ? [var.alert_email] : []
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = var.alert_email != "" ? [var.alert_email] : []
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.alert_email != "" ? [var.alert_email] : []
  }
}

# ──────────────────────────────────────────────
# CloudWatch Dashboard
# ──────────────────────────────────────────────
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "cloudtrain-${var.env}"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.jobs_queue_name, { label = "Jobs Queue Depth" }],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.jobs_dlq_name, { label = "Jobs DLQ Depth", color = "#d62728" }],
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", var.status_dlq_name, { label = "Status DLQ Depth", color = "#ff7f0e" }]
          ]
          period = 300
          stat   = "Maximum"
          region = var.region
          title  = "SQS Queue Depths"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiId", var.api_id, { label = "API Request Count" }],
            ["AWS/ApiGateway", "4XXError", "ApiId", var.api_id, { label = "4XX Errors", color = "#ffbb78" }],
            ["AWS/ApiGateway", "5XXError", "ApiId", var.api_id, { label = "5XX Errors", color = "#d62728" }]
          ]
          period = 300
          stat   = "Sum"
          region = var.region
          title  = "API Gateway Traffic & Errors"
        }
      }
    ]
  })
}
