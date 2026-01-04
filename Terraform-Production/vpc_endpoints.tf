# ============================================================================
# VPC ENDPOINTS
# ============================================================================

# S3 Gateway Endpoint
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [data.aws_route_table.lambda_subnet.id]

  tags = {
    Name = "S3 VPC Endpoint - Production"
  }
}

# DynamoDB Gateway Endpoint
resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [data.aws_route_table.lambda_subnet.id]

  tags = {
    Name = "DynamoDB VPC Endpoint - Production"
  }
}

# Secrets Manager Interface Endpoint
resource "aws_vpc_endpoint" "secretsmanager" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [var.lambda_subnet_id]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = {
    Name = "Secrets Manager VPC Endpoint - Production"
  }
}

# CloudWatch Logs Interface Endpoint
resource "aws_vpc_endpoint" "logs" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [var.lambda_subnet_id]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = {
    Name = "CloudWatch Logs VPC Endpoint - Production"
  }
}

# CloudWatch Monitoring Interface Endpoint
resource "aws_vpc_endpoint" "monitoring" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.monitoring"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [var.lambda_subnet_id]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = {
    Name = "CloudWatch Monitoring VPC Endpoint - Production"
  }
}

# SNS Interface Endpoint
resource "aws_vpc_endpoint" "sns" {
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.sns"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [var.lambda_subnet_id]
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true

  tags = {
    Name = "SNS VPC Endpoint - Production"
  }
}
