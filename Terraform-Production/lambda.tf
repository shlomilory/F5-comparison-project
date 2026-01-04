# ============================================================================
# LAMBDA FUNCTION
# ============================================================================

resource "aws_lambda_function" "f5_comparison" {
  filename         = var.lambda_package_path
  function_name    = var.lambda_function_name
  role            = aws_iam_role.lambda.arn
  handler         = "lambda_function.lambda_handler"
  source_code_hash = filebase64sha256(var.lambda_package_path)
  runtime         = "python3.11"
  timeout         = 120
  memory_size     = 512

  vpc_config {
    subnet_ids         = [var.lambda_subnet_id]
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      S3_BUCKET_NAME      = aws_s3_bucket.reports.id
      SECRET_NAME         = aws_secretsmanager_secret.f5_credentials.name
      SNS_TOPIC_ARN       = aws_sns_topic.f5_comparison.arn
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.comparison_history.name
      TEAMS_WEBHOOK_URL   = var.teams_webhook_url
      SERVER1             = var.f5_nj_ip
      SERVER2             = var.f5_hrz_ip
      CONFIG_PATH         = "/config/bigip.conf"
    }
  }

  tags = {
    Name = "F5 Comparison Lambda - Production"
  }
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = 30

  tags = {
    Name = "F5 Comparison Lambda Logs - Production"
  }
}
