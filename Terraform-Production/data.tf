# ============================================================================
# DATA SOURCES
# ============================================================================

data "aws_vpc" "production" {
  id = var.vpc_id
}

data "aws_subnet" "lambda_subnet" {
  id = var.lambda_subnet_id
}

# Get route table associated with the subnet
data "aws_route_table" "lambda_subnet" {
  subnet_id = var.lambda_subnet_id
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
