terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "mdekort-tfstate"
    key            = "network-monitor.tfstate"
    region         = "eu-west-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

provider "aws" {
  region = var.aws_region

  # Will assume role into network-monitor account
  assume_role {
    role_arn = "arn:aws:iam::${var.account_id}:role/OrganizationAccountAccessRole"
  }

  default_tags {
    tags = {
      Project     = "network-monitor"
      ManagedBy   = "Terraform"
      Repository  = "github.com/melvyndekort/network-monitor"
      Environment = "production"
    }
  }
}
