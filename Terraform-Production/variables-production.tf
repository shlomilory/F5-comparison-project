# ============================================================================
# PRODUCTION VARIABLES - F5 Configuration Comparison
# ============================================================================

variable "aws_region" {
  description = "AWS region for production deployment"
  type        = string
  default     = "eu-west-1"
}

variable "vpc_id" {
  description = "Production VPC ID"
  type        = string
  default     = "vpc-09d5a32669757a42e"
}

variable "lambda_subnet_id" {
  description = "Private subnet ID for Lambda function"
  type        = string
  default     = "subnet-0e1b4b559ca6abac4"
}

variable "s3_bucket_name" {
  description = "S3 bucket name for comparison reports"
  type        = string
  default     = "f5-comparison-reports-prod"
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for comparison history"
  type        = string
  default     = "f5-comparison-history-prod"
}

variable "secret_name" {
  description = "Secrets Manager secret name for F5 SSH credentials"
  type        = string
  default     = "f5_comparison_production_secrets"
}

variable "lambda_function_name" {
  description = "Lambda function name"
  type        = string
  default     = "f5-config-comparison-prod"
}

variable "lambda_package_path" {
  description = "Path to Lambda deployment package"
  type        = string
  default     = "./lambda_deployment.zip"
}

variable "f5_nj_ip" {
  description = "F5 server IP address in NJ datacenter"
  type        = string
  default     = "10.100.100.171"
}

variable "f5_hrz_ip" {
  description = "F5 server IP address in HRZ datacenter"
  type        = string
  default     = "10.200.100.171"
}

variable "teams_webhook_url" {
  description = "Microsoft Teams webhook URL for notifications"
  type        = string
  default     = "https://defaultdecee90cce03461e8c21dd538e181c.75.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/c40decabc8ab41b1b66cecda0753433b/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=HBxN4IltPwK9zThuNL8W94FMhDCFS4dtV6sTPDvJ24Q"
  sensitive   = true
}
