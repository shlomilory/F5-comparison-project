terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  profile = "Infrastructure-442028787335"
  default_tags {
    tags = {
      Environment = "production"
      Project     = "F5-Config-Comparison"
      ManagedBy   = "Terraform"
      Owner       = "DevOps-Infra"
    }
  }
}
