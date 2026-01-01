# DynamoDB Table for F5 Comparison Metadata
resource "aws_dynamodb_table" "f5_comparison_history" {
  name           = "f5-comparison-history"
  billing_mode   = "PAY_PER_REQUEST" # On-demand pricing (free tier eligible!)
  hash_key       = "comparison_id"
  range_key      = "timestamp"

  attribute {
    name = "comparison_id"
    type = "S" # String: "server1_vs_server2"
  }

  attribute {
    name = "timestamp"
    type = "S" # String: ISO timestamp
  }

  attribute {
    name = "virtual_server"
    type = "S" # For querying by virtual server name
  }

  # Global Secondary Index for querying by virtual server
  global_secondary_index {
    name            = "VirtualServerIndex"
    hash_key        = "virtual_server"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  # Enable point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }

  # Enable TTL for automatic cleanup (optional)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name        = "f5-comparison-history"
    Environment = var.environment
    Project     = "F5ConfigComparison"
  }
}

# Grant Lambda access to DynamoDB
resource "aws_iam_policy" "lambda_dynamodb" {
  name        = "f5-lambda-dynamodb-policy"
  description = "Allow Lambda to read/write to DynamoDB"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem"
        ]
        Resource = [
          aws_dynamodb_table.f5_comparison_history.arn,
          "${aws_dynamodb_table.f5_comparison_history.arn}/index/*"
        ]
      }
    ]
  })
}

# Attach policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_dynamodb" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.lambda_dynamodb.arn
}

# Output
output "dynamodb_table_name" {
  description = "DynamoDB table name for comparison history"
  value       = aws_dynamodb_table.f5_comparison_history.name
}

output "dynamodb_table_arn" {
  description = "DynamoDB table ARN"
  value       = aws_dynamodb_table.f5_comparison_history.arn
}