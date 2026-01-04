# ============================================================================
# CLOUDWATCH ALARMS
# ============================================================================

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "f5-comparison-lambda-errors-prod"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Alert when Lambda function has errors"
  alarm_actions       = [aws_sns_topic.f5_comparison.arn]

  dimensions = {
    FunctionName = aws_lambda_function.f5_comparison.function_name
  }

  tags = {
    Name = "F5 Comparison Lambda Errors - Production"
  }
}

resource "aws_cloudwatch_metric_alarm" "high_critical_count" {
  alarm_name          = "f5-comparison-high-critical-count-prod"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "CriticalPercentage"
  namespace           = "F5/ConfigComparison"
  period              = 300
  statistic           = "Maximum"
  threshold           = 5.0
  alarm_description   = "Alert when critical percentage exceeds 5%"
  alarm_actions       = [aws_sns_topic.f5_comparison.arn]

  tags = {
    Name = "F5 High Critical Count - Production"
  }
}
