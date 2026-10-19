# ──────────────────────────────────────────────
# 1. Network Module (VPC, Subnets, S3 Endpoint, Trainer SG)
# ──────────────────────────────────────────────
module "network" {
  source = "./modules/network"

  env    = var.env
  region = var.region
}

# ──────────────────────────────────────────────
# 2. Storage Module (Data & Web S3 Buckets)
# ──────────────────────────────────────────────
module "storage" {
  source = "./modules/storage"

  env                     = var.env
  artifact_retention_days = var.artifact_retention_days
  enable_local_cors       = var.enable_local_cors
}

# ──────────────────────────────────────────────
# 3. Database Module (DynamoDB Tables & Capacity Seed)
# ──────────────────────────────────────────────
module "database" {
  source = "./modules/database"

  env = var.env
}

# ──────────────────────────────────────────────
# 4. Messaging Module (SQS Jobs, Status, DLQs)
# ──────────────────────────────────────────────
module "messaging" {
  source = "./modules/messaging"

  env              = var.env
  trainer_role_arn = module.compute.trainer_role_arn
}

# ──────────────────────────────────────────────
# 5. Compute Module (EC2 Launch Template, Trainer IAM, Logs)
# ──────────────────────────────────────────────
module "compute" {
  source = "./modules/compute"

  env                       = var.env
  region                    = var.region
  data_bucket_name          = module.storage.data_bucket_id
  data_bucket_arn           = module.storage.data_bucket_arn
  status_queue_arn          = module.messaging.status_queue_arn
  trainer_security_group_id = module.network.trainer_security_group_id
  instance_type_small       = var.instance_type_small
  instance_type_medium      = var.instance_type_medium
  log_retention_days        = var.log_retention_days
  use_spot                  = var.use_spot
}

# ──────────────────────────────────────────────
# 6. Lambdas Module (7 Serverless Functions)
# ──────────────────────────────────────────────
module "lambdas" {
  source = "./modules/lambdas"

  env                       = var.env
  region                    = var.region
  data_bucket_id            = module.storage.data_bucket_id
  data_bucket_arn           = module.storage.data_bucket_arn
  jobs_table_name           = module.database.jobs_table_name
  jobs_table_arn            = module.database.jobs_table_arn
  datasets_table_name       = module.database.datasets_table_name
  datasets_table_arn        = module.database.datasets_table_arn
  jobs_queue_arn            = module.messaging.jobs_queue_arn
  jobs_queue_url            = module.messaging.jobs_queue_url
  jobs_dlq_arn              = module.messaging.jobs_dlq_arn
  status_queue_arn          = module.messaging.status_queue_arn
  status_queue_url          = module.messaging.status_queue_url
  launch_template_id        = module.compute.launch_template_id
  subnet_ids                = module.network.public_subnet_ids
  trainer_security_group_id = module.network.trainer_security_group_id
  trainer_role_arn          = module.compute.trainer_role_arn
  ecr_repository_url        = var.ecr_repository_url
  trainer_image_tag         = var.trainer_image_tag
  max_concurrent_instances  = var.max_concurrent_instances
  max_runtime_minutes       = var.max_runtime_minutes
  allowed_email_domains     = var.allowed_email_domains
  allowed_emails            = var.allowed_emails
  log_retention_days        = var.log_retention_days
}

# ──────────────────────────────────────────────
# 7. Auth Module (Cognito User Pool & Client)
# ──────────────────────────────────────────────
module "auth" {
  source = "./modules/auth"

  env                   = var.env
  pre_signup_lambda_arn = module.lambdas.pre_signup_lambda_arn
}

# ──────────────────────────────────────────────
# 8. API Module (API Gateway HTTP API & Routes)
# ──────────────────────────────────────────────
module "api" {
  source = "./modules/api"

  env                 = var.env
  region              = var.region
  api_lambda_arn      = module.lambdas.api_lambda_arn
  api_lambda_name     = module.lambdas.api_lambda_name
  user_pool_id        = module.auth.user_pool_id
  user_pool_client_id = module.auth.user_pool_client_id
  enable_local_cors   = var.enable_local_cors
  log_retention_days  = var.log_retention_days
}

# ──────────────────────────────────────────────
# 9. Frontend Module (CloudFront CDN & Config)
# ──────────────────────────────────────────────
module "frontend" {
  source = "./modules/frontend"

  env                             = var.env
  region                          = var.region
  web_bucket_id                   = module.storage.web_bucket_id
  web_bucket_arn                  = module.storage.web_bucket_arn
  web_bucket_regional_domain_name = module.storage.web_bucket_regional_domain_name
  api_endpoint                    = module.api.api_endpoint
  user_pool_id                    = module.auth.user_pool_id
  user_pool_client_id             = module.auth.user_pool_client_id
}

# ──────────────────────────────────────────────
# 10. Observability Module (Alarms, Dashboard, Budget)
# ──────────────────────────────────────────────
module "observability" {
  source = "./modules/observability"

  env                = var.env
  region             = var.region
  alert_email        = var.alert_email
  monthly_budget_usd = var.monthly_budget_usd
  jobs_queue_name    = "cloudtrain-${var.env}-jobs"
  jobs_dlq_name      = "cloudtrain-${var.env}-jobs-dlq"
  status_dlq_name    = "cloudtrain-${var.env}-status-dlq"
  api_id             = module.api.api_id
}
