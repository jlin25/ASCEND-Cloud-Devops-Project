terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Credentials are read automatically from the standard AWS chain:
#   1. env vars (AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY)
#   2. ~/.aws/credentials  (created by `aws configure`)
#   3. an IAM role, when running on AWS
provider "aws" {
  region = var.aws_region
}
