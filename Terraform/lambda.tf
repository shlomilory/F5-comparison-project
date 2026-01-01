# Lambda Function for F5 Configuration Comparison

# IAM Role for Lambda
resource "aws_iam_role" "lambda" {
  name = "f5-config-comparison-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      },
    ]
  })

  tags = merge(local.common_tags, {
    Name = "f5-lambda-role"
  })
}

# IAM Policy for Lambda
resource "aws_iam_role_policy" "lambda" {
  name = "f5-lambda-policy"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 access
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.reports.arn,
          "${aws_s3_bucket.reports.arn}/*"
        ]
      },
      # CloudWatch Metrics (ADD THIS NEW BLOCK!)
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      },
      # Secrets Manager access
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.ssh_credentials.arn,
          aws_secretsmanager_secret.teams_webhook.arn
        ]
      },
      # SNS access
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.notifications.arn
      },
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # VPC networking
      {
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface"
        ]
        Resource = "*"
      }
    ]
  })
}

# Lambda Function
resource "aws_lambda_function" "f5_comparison" {
  filename         = "${path.module}/../lambda_deployment.zip"
  function_name    = "f5-config-comparison"
  role             = aws_iam_role.lambda.arn
  handler          = "lambda_function.lambda_handler"
  source_code_hash = filebase64sha256("${path.module}/../lambda_deployment.zip")
  runtime          = "python3.11"
  timeout          = 90
  memory_size      = 512

  vpc_config {
    subnet_ids         = [aws_subnet.private.id]
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      S3_BUCKET_NAME   = aws_s3_bucket.reports.id
      SECRET_NAME      = aws_secretsmanager_secret.ssh_credentials.name
      SNS_TOPIC_ARN    = aws_sns_topic.notifications.arn
      TEAMS_SECRET_NAME = aws_secretsmanager_secret.teams_webhook.name
      SERVER1          = var.f5_server1_ip
      SERVER2          = var.f5_server2_ip
      CONFIG_PATH      = var.f5_config_path
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.f5_comparison_history.name
    }
  }

  tags = merge(local.common_tags, {
    Name = "f5-config-comparison"
  })

  depends_on = [aws_iam_role_policy.lambda]
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.f5_comparison.function_name}"
  retention_in_days = 14

  tags = merge(local.common_tags, {
    Name = "f5-lambda-logs"
  })
}

# EventBridge Rule for scheduled execution
resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "f5-config-comparison-schedule"
  description         = "Trigger F5 configuration comparison daily"
  schedule_expression = var.lambda_schedule

  tags = merge(local.common_tags, {
    Name = "f5-schedule"
  })
}

# EventBridge Target
resource "aws_cloudwatch_event_target" "lambda" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "f5-lambda"
  arn       = aws_lambda_function.f5_comparison.arn
}

# Lambda Permission for EventBridge
resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.f5_comparison.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}
