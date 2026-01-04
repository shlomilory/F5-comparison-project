# ============================================================================
# SECURITY GROUPS
# ============================================================================

# Lambda Security Group
resource "aws_security_group" "lambda" {
  name        = "f5-comparison-lambda-sg-prod"
  description = "Security group for F5 comparison Lambda function - Production"
  vpc_id      = var.vpc_id

  # Outbound to F5 servers (SSH)
  egress {
    description = "SSH to F5 NJ"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["${var.f5_nj_ip}/32"]
  }

  egress {
    description = "SSH to F5 HRZ"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["${var.f5_hrz_ip}/32"]
  }

  # Outbound to VPC endpoints (HTTPS)
  egress {
    description = "HTTPS to VPC Endpoints"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.production.cidr_block]
  }

  # Outbound to Teams webhook
  egress {
    description = "HTTPS to Teams Webhook"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "F5 Comparison Lambda SG - Production"
  }
}

# Security Group for VPC Endpoints
resource "aws_security_group" "vpc_endpoints" {
  name        = "f5-vpc-endpoints-sg-prod"
  description = "Security group for VPC endpoints - Production"
  vpc_id      = var.vpc_id

  ingress {
    description     = "HTTPS from Lambda"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  egress {
    description = "Allow all outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "VPC Endpoints SG - Production"
  }
}
