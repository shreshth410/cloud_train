data "aws_partition" "current" {}
data "aws_caller_identity" "current" {}

# Placeholder zip archive for terraform validation and initial plan
data "archive_file" "placeholder" {
  type        = "zip"
  output_path = "${path.module}/placeholder.zip"

  source {
    content  = "def handler(event, context):\n    return {'statusCode': 200, 'body': 'OK'}\n"
    filename = "main.py"
  }
}

locals {
  lambda_assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# ──────────────────────────────────────────────
# 1. API Lambda
# ──────────────────────────────────────────────
resource "aws_iam_role" "api" {
  name               = "cloudtrain-${var.env}-api-role"
  assume_role_policy = local.lambda_assume_role_policy
}

resource "aws_iam_role_policy" "api" {
  name = "cloudtrain-api-policy"
  role = aws_iam_role.api.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          var.jobs_table_arn,
          "${var.jobs_table_arn}/*",
          var.datasets_table_arn,
          "${var.datasets_table_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Resource = [
          "${var.data_bucket_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = var.jobs_queue_arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.api.arn}:*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/cloudtrain-${var.env}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name = "cloudtrain-${var.env}-api"
  role          = aws_iam_role.api.arn
  handler       = "main.handler"
  runtime       = "python3.12"
  memory_size   = 256
  timeout       = 30

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = {
      ENV            = var.env
      REGION         = var.region
      JOBS_TABLE     = var.jobs_table_name
      DATASETS_TABLE = var.datasets_table_name
      DATA_BUCKET    = var.data_bucket_id
      JOBS_QUEUE_URL = var.jobs_queue_url
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

# ──────────────────────────────────────────────
# 2. Dataset Profiler Lambda
# ──────────────────────────────────────────────
resource "aws_iam_role" "dataset_profiler" {
  name               = "cloudtrain-${var.env}-profiler-role"
  assume_role_policy = local.lambda_assume_role_policy
}

resource "aws_iam_role_policy" "dataset_profiler" {
  name = "cloudtrain-profiler-policy"
  role = aws_iam_role.dataset_profiler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          var.datasets_table_arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = [
          "${var.data_bucket_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.dataset_profiler.arn}:*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "dataset_profiler" {
  name              = "/aws/lambda/cloudtrain-${var.env}-dataset-profiler"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "dataset_profiler" {
  function_name = "cloudtrain-${var.env}-dataset-profiler"
  role          = aws_iam_role.dataset_profiler.arn
  handler       = "main.handler"
  runtime       = "python3.12"
  memory_size   = 512
  timeout       = 300

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = {
      ENV            = var.env
      REGION         = var.region
      DATASETS_TABLE = var.datasets_table_name
      DATA_BUCKET    = var.data_bucket_id
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_permission" "profiler_s3" {
  statement_id  = "AllowS3BucketNotification"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.dataset_profiler.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.data_bucket_arn
}

# S3 ObjectCreated Notification to trigger dataset_profiler
resource "aws_s3_bucket_notification" "profiler_notification" {
  bucket = var.data_bucket_id

  lambda_function {
    lambda_function_arn = aws_lambda_function.dataset_profiler.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "datasets/"
  }

  depends_on = [aws_lambda_permission.profiler_s3]
}

# ──────────────────────────────────────────────
# 3. Job Launcher Lambda
# ──────────────────────────────────────────────
resource "aws_iam_role" "job_launcher" {
  name               = "cloudtrain-${var.env}-launcher-role"
  assume_role_policy = local.lambda_assume_role_policy
}

resource "aws_iam_role_policy" "job_launcher" {
  name = "cloudtrain-launcher-policy"
  role = aws_iam_role.job_launcher.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          var.jobs_table_arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = [
          "${var.data_bucket_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = var.jobs_queue_arn
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:RunInstances",
          "ec2:CreateTags",
          "ec2:DescribeInstances"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "iam:PassRole"
        ]
        Resource = var.trainer_role_arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.job_launcher.arn}:*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "job_launcher" {
  name              = "/aws/lambda/cloudtrain-${var.env}-job-launcher"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "job_launcher" {
  function_name = "cloudtrain-${var.env}-job-launcher"
  role          = aws_iam_role.job_launcher.arn
  handler       = "main.handler"
  runtime       = "python3.12"
  memory_size   = 256
  timeout       = 60

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = {
      ENV                      = var.env
      REGION                   = var.region
      JOBS_TABLE               = var.jobs_table_name
      DATA_BUCKET              = var.data_bucket_id
      STATUS_QUEUE_URL         = var.status_queue_url
      LAUNCH_TEMPLATE_ID       = var.launch_template_id
      SUBNET_IDS               = join(",", var.subnet_ids)
      SECURITY_GROUP_ID        = var.trainer_security_group_id
      ECR_REPO_URL             = var.ecr_repository_url
      TRAINER_IMAGE_TAG        = var.trainer_image_tag
      MAX_CONCURRENT_INSTANCES = tostring(var.max_concurrent_instances)
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_event_source_mapping" "jobs_queue" {
  event_source_arn = var.jobs_queue_arn
  function_name    = aws_lambda_function.job_launcher.arn
  batch_size       = 1
  enabled          = true
}

# ──────────────────────────────────────────────
# 4. Status Updater Lambda
# ──────────────────────────────────────────────
resource "aws_iam_role" "status_updater" {
  name               = "cloudtrain-${var.env}-updater-role"
  assume_role_policy = local.lambda_assume_role_policy
}

resource "aws_iam_role_policy" "status_updater" {
  name = "cloudtrain-updater-policy"
  role = aws_iam_role.status_updater.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          var.jobs_table_arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = var.status_queue_arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.status_updater.arn}:*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "status_updater" {
  name              = "/aws/lambda/cloudtrain-${var.env}-status-updater"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "status_updater" {
  function_name = "cloudtrain-${var.env}-status-updater"
  role          = aws_iam_role.status_updater.arn
  handler       = "main.handler"
  runtime       = "python3.12"
  memory_size   = 128
  timeout       = 30

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = {
      ENV        = var.env
      REGION     = var.region
      JOBS_TABLE = var.jobs_table_name
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_event_source_mapping" "status_queue" {
  event_source_arn                   = var.status_queue_arn
  function_name                      = aws_lambda_function.status_updater.arn
  batch_size                         = 10
  maximum_batching_window_in_seconds = 2
  enabled                            = true
}

# ──────────────────────────────────────────────
# 5. DLQ Reaper Lambda
# ──────────────────────────────────────────────
resource "aws_iam_role" "dlq_reaper" {
  name               = "cloudtrain-${var.env}-reaper-role"
  assume_role_policy = local.lambda_assume_role_policy
}

resource "aws_iam_role_policy" "dlq_reaper" {
  name = "cloudtrain-reaper-policy"
  role = aws_iam_role.dlq_reaper.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem"
        ]
        Resource = [
          var.jobs_table_arn
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = var.jobs_dlq_arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.dlq_reaper.arn}:*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "dlq_reaper" {
  name              = "/aws/lambda/cloudtrain-${var.env}-dlq-reaper"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "dlq_reaper" {
  function_name = "cloudtrain-${var.env}-dlq-reaper"
  role          = aws_iam_role.dlq_reaper.arn
  handler       = "main.handler"
  runtime       = "python3.12"
  memory_size   = 128
  timeout       = 30

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = {
      ENV        = var.env
      REGION     = var.region
      JOBS_TABLE = var.jobs_table_name
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_event_source_mapping" "jobs_dlq" {
  event_source_arn = var.jobs_dlq_arn
  function_name    = aws_lambda_function.dlq_reaper.arn
  batch_size       = 1
  enabled          = true
}

# ──────────────────────────────────────────────
# 6. Watchdog Lambda
# ──────────────────────────────────────────────
resource "aws_iam_role" "watchdog" {
  name               = "cloudtrain-${var.env}-watchdog-role"
  assume_role_policy = local.lambda_assume_role_policy
}

resource "aws_iam_role_policy" "watchdog" {
  name = "cloudtrain-watchdog-policy"
  role = aws_iam_role.watchdog.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = [
          var.jobs_table_arn,
          "${var.jobs_table_arn}/*",
          var.datasets_table_arn,
          "${var.datasets_table_arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:TerminateInstances"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.watchdog.arn}:*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "watchdog" {
  name              = "/aws/lambda/cloudtrain-${var.env}-watchdog"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "watchdog" {
  function_name = "cloudtrain-${var.env}-watchdog"
  role          = aws_iam_role.watchdog.arn
  handler       = "main.handler"
  runtime       = "python3.12"
  memory_size   = 128
  timeout       = 60

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = {
      ENV                 = var.env
      REGION              = var.region
      JOBS_TABLE          = var.jobs_table_name
      DATASETS_TABLE      = var.datasets_table_name
      DATA_BUCKET         = var.data_bucket_id
      MAX_RUNTIME_MINUTES = tostring(var.max_runtime_minutes)
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

# EventBridge Schedule: Run Watchdog every 5 minutes
resource "aws_cloudwatch_event_rule" "watchdog_schedule" {
  name                = "cloudtrain-${var.env}-watchdog-rule"
  description         = "Periodic execution of CloudTrain capacity and orphan watchdog"
  schedule_expression = "rate(5 minutes)"
}

resource "aws_cloudwatch_event_target" "watchdog_target" {
  rule      = aws_cloudwatch_event_rule.watchdog_schedule.name
  target_id = "WatchdogLambdaTarget"
  arn       = aws_lambda_function.watchdog.arn
}

resource "aws_lambda_permission" "watchdog_eventbridge" {
  statement_id  = "AllowEventBridgeWatchdog"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.watchdog.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.watchdog_schedule.arn
}

# ──────────────────────────────────────────────
# 7. Pre-Signup Lambda (Cognito Gatekeeper)
# ──────────────────────────────────────────────
resource "aws_iam_role" "pre_signup" {
  name               = "cloudtrain-${var.env}-pre-signup-role"
  assume_role_policy = local.lambda_assume_role_policy
}

resource "aws_iam_role_policy" "pre_signup" {
  name = "cloudtrain-pre-signup-policy"
  role = aws_iam_role.pre_signup.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${aws_cloudwatch_log_group.pre_signup.arn}:*"
      }
    ]
  })
}

resource "aws_cloudwatch_log_group" "pre_signup" {
  name              = "/aws/lambda/cloudtrain-${var.env}-pre-signup"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "pre_signup" {
  function_name = "cloudtrain-${var.env}-pre-signup"
  role          = aws_iam_role.pre_signup.arn
  handler       = "main.handler"
  runtime       = "python3.12"
  memory_size   = 128
  timeout       = 10

  filename         = data.archive_file.placeholder.output_path
  source_code_hash = data.archive_file.placeholder.output_base64sha256

  environment {
    variables = {
      ENV                   = var.env
      ALLOWED_EMAIL_DOMAINS = jsonencode(var.allowed_email_domains)
      ALLOWED_EMAILS        = jsonencode(var.allowed_emails)
    }
  }

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_permission" "cognito_pre_signup" {
  statement_id  = "AllowCognitoInvocation"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.pre_signup.function_name
  principal     = "cognito-idp.amazonaws.com"
}
