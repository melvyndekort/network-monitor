terraform {
  required_version = "~> 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
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

provider "aws" {
  region = "us-east-1"
  alias  = "useast1"

  default_tags {
    tags = {
      Project     = "network-monitor"
      ManagedBy   = "Terraform"
      Repository  = "github.com/melvyndekort/network-monitor"
      Environment = "production"
    }
  }
}

provider "cloudflare" {
  api_token = data.terraform_remote_state.tf_cloudflare.outputs.api_token_network_monitor
}
