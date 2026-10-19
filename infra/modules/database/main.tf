# ──────────────────────────────────────────────
# DynamoDB: datasets table
# ──────────────────────────────────────────────
resource "aws_dynamodb_table" "datasets" {
  name         = "cloudtrain-${var.env}-datasets"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "dataset_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "dataset_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "status-created_at"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = false # Cost guardrail: disabled for zero-cost baseline
  }

  tags = {
    Name = "cloudtrain-${var.env}-datasets"
  }
}

# ──────────────────────────────────────────────
# DynamoDB: jobs table
# ──────────────────────────────────────────────
resource "aws_dynamodb_table" "jobs" {
  name         = "cloudtrain-${var.env}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"
  range_key    = "job_id"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "job_id"
    type = "S"
  }

  attribute {
    name = "status"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "status-created_at"
    hash_key        = "status"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = false # Cost guardrail: disabled for zero-cost baseline
  }

  tags = {
    Name = "cloudtrain-${var.env}-jobs"
  }
}

# ──────────────────────────────────────────────
# Atomic Capacity Slot Seed Item (__capacity__)
# ──────────────────────────────────────────────
resource "aws_dynamodb_table_item" "capacity" {
  table_name = aws_dynamodb_table.jobs.name
  hash_key   = aws_dynamodb_table.jobs.hash_key
  range_key  = aws_dynamodb_table.jobs.range_key

  item = jsonencode({
    user_id = { S = "__capacity__" }
    job_id  = { S = "__capacity__" }
    in_use  = { N = "0" }
  })

  lifecycle {
    ignore_changes = [item]
  }
}
