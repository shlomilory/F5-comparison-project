# Input Variables

variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, test, prod)"
  type        = string
  default     = "dev"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for public subnet (VPN server)"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for private subnet (Lambda)"
  type        = string
  default     = "10.0.2.0/24"
}

variable "home_network_cidr" {
  description = "CIDR block of your home network"
  type        = string
  default     = "10.100.102.0/24"
}

variable "f5_server1_ip" {
  description = "IP address of F5 server 1"
  type        = string
  default     = "10.100.102.10"
}

variable "f5_server2_ip" {
  description = "IP address of F5 server 2"
  type        = string
  default     = "10.100.102.12"
}

variable "f5_config_path" {
  description = "Path to F5 configuration file on servers"
  type        = string
  default     = "/home/vboxuser/bigip.conf"
}

variable "f5_ssh_username" {
  description = "SSH username for F5 servers"
  type        = string
  default     = "vboxuser"
}

variable "vpn_instance_type" {
  description = "EC2 instance type for VPN server"
  type        = string
  default     = "t3.micro"
}

variable "lambda_schedule" {
  description = "Cron expression for Lambda execution schedule"
  type        = string
  default     = "cron(0 2 * * ? *)" # Daily at 2 AM UTC
}

variable "teams_webhook_url" {
  description = "Microsoft Teams webhook URL for notifications"
  type        = string
  sensitive   = true
}

variable "ssh_private_key" {
  description = "SSH private key for accessing F5 servers"
  type        = string
  sensitive   = true
}

variable "s3_lifecycle_days" {
  description = "Number of days to retain S3 objects before deletion"
  type        = number
  default     = 30
}

variable "enable_vpn" {
  description = "Whether to deploy VPN server (set to false for testing without VPN)"
  type        = bool
  default     = true
}
