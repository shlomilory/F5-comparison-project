# VPC and Networking Resources

# VPC
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(local.common_tags, {
    Name = "f5-comparison-vpc"
  })
}

# Internet Gateway
resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = merge(local.common_tags, {
    Name = "f5-comparison-igw"
  })
}

# Public Subnet (for VPN server)
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = merge(local.common_tags, {
    Name = "f5-public-subnet"
    Type = "Public"
  })
}

# Private Subnet (for Lambda)
resource "aws_subnet" "private" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidr
  availability_zone = data.aws_availability_zones.available.names[0]

  tags = merge(local.common_tags, {
    Name = "f5-private-subnet"
    Type = "Private"
  })
}

# Public Route Table
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  tags = merge(local.common_tags, {
    Name = "f5-public-rt"
  })
}

# Public Route - Internet access
resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.main.id
}

# Public Subnet Association
resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Private Route Table
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  tags = merge(local.common_tags, {
    Name = "f5-private-rt"
  })
}

# Private Route - to home network via VPN server
resource "aws_route" "private_to_home" {
  count = var.enable_vpn ? 1 : 0
  
  route_table_id         = aws_route_table.private.id
  destination_cidr_block = var.home_network_cidr
  network_interface_id   = aws_instance.vpn_server[0].primary_network_interface_id
  
  depends_on = [aws_instance.vpn_server]
}

# Private Subnet Association
resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}

# Security Group for VPN Server
resource "aws_security_group" "vpn_server" {
  count = var.enable_vpn ? 1 : 0
  
  name        = "f5-vpn-server-sg"
  description = "Security group for OpenVPN server"
  vpc_id      = aws_vpc.main.id

  # OpenVPN port from your IP
  ingress {
    description = "OpenVPN from my IP"
    from_port   = 1194
    to_port     = 1194
    protocol    = "udp"
    cidr_blocks = [local.my_ip]
  }

  # SSH from your IP
  ingress {
    description = "SSH from my IP"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [local.my_ip]
  }

  # All traffic within VPC
  ingress {
    description = "All traffic within VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  # Allow traffic from Lambda
  ingress {
    description     = "Traffic from Lambda"
    from_port       = 0
    to_port         = 0
    protocol        = "-1"
    security_groups = [aws_security_group.lambda.id]
  }

  # Outbound - all traffic
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "f5-vpn-server-sg"
  })
}

# Security Group for Lambda
resource "aws_security_group" "lambda" {
  name        = "f5-lambda-sg"
  description = "Security group for Lambda function"
  vpc_id      = aws_vpc.main.id

  # Lambda needs to reach VPC endpoints
  ingress {
    description = "HTTPS from self (for VPC endpoints)"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    self        = true
  }

  # Outbound - all traffic (Lambda needs to reach VPN server, S3, Secrets Manager, SNS)
  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "f5-lambda-sg"
  })
}

# VPC Endpoints for Lambda (so it can access AWS services without NAT)
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = merge(local.common_tags, {
    Name = "f5-s3-endpoint"
  })
}

resource "aws_vpc_endpoint" "secrets_manager" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.private.id]
  security_group_ids  = [aws_security_group.lambda.id]
  private_dns_enabled = true

  tags = merge(local.common_tags, {
    Name = "f5-secrets-manager-endpoint"
  })
}

# DynamoDB VPC Endpoint
resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  
  route_table_ids = [
    aws_route_table.private.id
  ]

  tags = merge(local.common_tags, {
    Name = "f5-dynamodb-endpoint"
  })
}

# CloudWatch Logs VPC Endpoint (for Lambda logging)
resource "aws_vpc_endpoint" "cloudwatch_logs" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.private.id]
  security_group_ids  = [aws_security_group.lambda.id]
  private_dns_enabled = true

  tags = merge(local.common_tags, {
    Name = "f5-cloudwatch-logs-endpoint"
  })
}

# CloudWatch Monitoring VPC Endpoint (for custom metrics)
resource "aws_vpc_endpoint" "cloudwatch_monitoring" {
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.monitoring"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [aws_subnet.private.id]
  security_group_ids  = [aws_security_group.lambda.id]
  private_dns_enabled = true

  tags = merge(local.common_tags, {
    Name = "f5-cloudwatch-monitoring-endpoint"
  })
}