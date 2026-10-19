data "aws_partition" "current" {}

# ──────────────────────────────────────────────
# AMI Lookup: Amazon Linux 2023 (x86_64)
# ──────────────────────────────────────────────
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

# ──────────────────────────────────────────────
# CloudWatch Log Group for Training
# ──────────────────────────────────────────────
resource "aws_cloudwatch_log_group" "training" {
  name              = "/cloudtrain/${var.env}/training"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "cloudtrain-${var.env}-training-logs"
  }
}

# ──────────────────────────────────────────────
# Trainer IAM Role & Instance Profile
# ──────────────────────────────────────────────
resource "aws_iam_role" "trainer" {
  name = "cloudtrain-${var.env}-trainer-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = {
    Name = "cloudtrain-${var.env}-trainer-role"
  }
}

# ECR Pull Policy
resource "aws_iam_role_policy" "trainer_ecr" {
  name = "cloudtrain-trainer-ecr"
  role = aws_iam_role.trainer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage"
        ]
        Resource = "*"
      }
    ]
  })
}

# S3 Access (Jobs config/artifacts and Datasets)
resource "aws_iam_role_policy" "trainer_s3" {
  name = "cloudtrain-trainer-s3"
  role = aws_iam_role.trainer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject"
        ]
        Resource = [
          "${var.data_bucket_arn}/datasets/*",
          "${var.data_bucket_arn}/jobs/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:HeadObject"
        ]
        Resource = [
          "${var.data_bucket_arn}/jobs/*"
        ]
      }
    ]
  })
}

# SQS Status Queue SendMessage
resource "aws_iam_role_policy" "trainer_sqs" {
  name = "cloudtrain-trainer-sqs"
  role = aws_iam_role.trainer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = var.status_queue_arn
      }
    ]
  })
}

# CloudWatch Logs PutLogEvents
resource "aws_iam_role_policy" "trainer_logs" {
  name = "cloudtrain-trainer-logs"
  role = aws_iam_role.trainer.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "${aws_cloudwatch_log_group.training.arn}:*"
      }
    ]
  })
}

# SSM Session Manager Core (Secure shell-free admin access)
resource "aws_iam_role_policy_attachment" "trainer_ssm" {
  role       = aws_iam_role.trainer.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "trainer" {
  name = "cloudtrain-${var.env}-trainer-profile"
  role = aws_iam_role.trainer.name
}

# ──────────────────────────────────────────────
# EC2 Launch Template (IMDSv2, Auto-Terminate)
# ──────────────────────────────────────────────
resource "aws_launch_template" "trainer" {
  name_prefix   = "cloudtrain-${var.env}-trainer-"
  image_id      = data.aws_ami.al2023.id
  instance_type = var.instance_type_small

  instance_initiated_shutdown_behavior = "terminate" # Cost Guardrail: self-terminating

  iam_instance_profile {
    arn = aws_iam_instance_profile.trainer.arn
  }

  network_interfaces {
    associate_public_ip_address = true
    security_groups             = [var.trainer_security_group_id]
    delete_on_termination       = true
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 mandatory
    http_put_response_hop_limit = 2          # Allows Docker container on host bridge to reach IMDSv2
    instance_metadata_tags      = "enabled"
  }

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_size           = 20
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  dynamic "instance_market_options" {
    for_each = var.use_spot ? [1] : []
    content {
      market_type = "spot"
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name      = "cloudtrain-${var.env}-trainer"
      Project   = "CloudTrain"
      ManagedBy = "Terraform"
    }
  }

  tags = {
    Name = "cloudtrain-${var.env}-trainer-template"
  }
}
