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
  
  default_tags {
    tags = {
      Environment = "production"
      Resource    = "F5_RESOURCE"
      Project     = "F5-Config-Comparison"
      ManagedBy   = "Terraform"
      Owner       = "DevOps"
    }
  }
}
