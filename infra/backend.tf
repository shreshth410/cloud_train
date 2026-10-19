terraform {
  backend "s3" {
    # Passed via -backend-config from CI or command line:
    # bucket         = "cloudtrain-tfstate-<account_id>"
    # key            = "cloudtrain/prod/terraform.tfstate"
    # region         = "ap-south-1"
    # use_lockfile   = true
    # encrypt        = true
  }
}
