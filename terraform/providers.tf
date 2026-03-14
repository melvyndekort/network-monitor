terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket       = "mdekort-tfstate-844347863910"
    key          = "network-monitor.tfstate"
    region       = "eu-west-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "network-monitor"
      ManagedBy   = "Terraform"
      Repository  = "github.com/melvyndekort/network-monitor"
      Environment = "production"
    }
  }
}
