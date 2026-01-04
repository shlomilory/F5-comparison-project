# ============================================================================
# DATA SOURCES
# ============================================================================

data "aws_vpc" "production" {
  id = var.vpc_id
}

data "aws_subnet" "lambda_subnet" {
  id = var.lambda_subnet_id
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
