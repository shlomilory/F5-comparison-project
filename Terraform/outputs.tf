# Terraform Outputs

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_id" {
  description = "ID of the public subnet"
  value       = aws_subnet.public.id
}

output "private_subnet_id" {
  description = "ID of the private subnet"
  value       = aws_subnet.private.id
}

output "vpn_server_public_ip" {
  description = "Public IP address of VPN server"
  value       = var.enable_vpn ? aws_eip.vpn_server[0].public_ip : "VPN disabled"
}

output "vpn_server_private_ip" {
  description = "Private IP address of VPN server"
  value       = var.enable_vpn ? aws_instance.vpn_server[0].private_ip : "VPN disabled"
}

output "s3_bucket_name" {
  description = "Name of S3 bucket for reports"
  value       = aws_s3_bucket.reports.id
}

output "lambda_function_name" {
  description = "Name of Lambda function"
  value       = aws_lambda_function.f5_comparison.function_name
}

output "lambda_function_arn" {
  description = "ARN of Lambda function"
  value       = aws_lambda_function.f5_comparison.arn
}

output "sns_topic_arn" {
  description = "ARN of SNS topic"
  value       = aws_sns_topic.notifications.arn
}

output "ssh_secret_name" {
  description = "Name of SSH credentials secret"
  value       = aws_secretsmanager_secret.ssh_credentials.name
}

output "teams_secret_name" {
  description = "Name of Teams webhook secret"
  value       = aws_secretsmanager_secret.teams_webhook.name
}

output "vpn_connection_instructions" {
  description = "Instructions for connecting to VPN"
  value       = var.enable_vpn ? "VPN Server deployed. SSH to server to configure client." : "VPN disabled - set enable_vpn = true to deploy VPN server"
}

output "test_lambda_command" {
  description = "AWS CLI command to test Lambda function"
  value       = "aws lambda invoke --function-name ${aws_lambda_function.f5_comparison.function_name} --region ${var.aws_region} response.json && cat response.json"
}

output "view_logs_command" {
  description = "AWS CLI command to view Lambda logs"
  value       = "aws logs tail /aws/lambda/${aws_lambda_function.f5_comparison.function_name} --follow --region ${var.aws_region}"
}

output "your_public_ip" {
  description = "Your detected public IP (whitelisted for VPN access)"
  value       = local.my_ip
}
