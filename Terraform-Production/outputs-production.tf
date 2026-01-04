# ============================================================================
# OUTPUTS - F5 Configuration Comparison Production
# ============================================================================

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.f5_comparison.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.f5_comparison.arn
}

output "s3_bucket_name" {
  description = "Name of the S3 bucket for reports"
  value       = aws_s3_bucket.reports.id
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket"
  value       = aws_s3_bucket.reports.arn
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table"
  value       = aws_dynamodb_table.comparison_history.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB table"
  value       = aws_dynamodb_table.comparison_history.arn
}

output "sns_topic_arn" {
  description = "ARN of the SNS topic for notifications"
  value       = aws_sns_topic.f5_comparison.arn
}

output "secrets_manager_secret_name" {
  description = "Name of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.f5_credentials.name
}

output "secrets_manager_secret_arn" {
  description = "ARN of the Secrets Manager secret"
  value       = aws_secretsmanager_secret.f5_credentials.arn
}

output "lambda_security_group_id" {
  description = "ID of the Lambda security group"
  value       = aws_security_group.lambda.id
}

output "vpc_endpoints" {
  description = "VPC endpoint IDs"
  value = {
    s3              = aws_vpc_endpoint.s3.id
    dynamodb        = aws_vpc_endpoint.dynamodb.id
    secretsmanager  = aws_vpc_endpoint.secretsmanager.id
    logs            = aws_vpc_endpoint.logs.id
    monitoring      = aws_vpc_endpoint.monitoring.id
    sns             = aws_vpc_endpoint.sns.id
  }
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.lambda.name
}

output "eventbridge_schedule" {
  description = "EventBridge schedule rule name"
  value       = aws_cloudwatch_event_rule.biannual_comparison.name
}

output "deployment_summary" {
  description = "Summary of deployment"
  value = {
    region              = var.aws_region
    vpc_id              = var.vpc_id
    lambda_subnet       = var.lambda_subnet_id
    f5_nj_ip           = var.f5_nj_ip
    f5_hrz_ip          = var.f5_hrz_ip
    lambda_function     = aws_lambda_function.f5_comparison.function_name
    s3_bucket          = aws_s3_bucket.reports.id
    dynamodb_table     = aws_dynamodb_table.comparison_history.name
    schedule           = "Biannual: Jan 1 & July 1 at 11:00 UTC (13:00 Israel time)"
  }
}
