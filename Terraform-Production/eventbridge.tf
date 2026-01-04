# ============================================================================
# EVENTBRIDGE SCHEDULE (BIANNUAL - JAN 1 & JULY 1 AT 11:00 UTC)
# ============================================================================

resource "aws_cloudwatch_event_rule" "biannual_comparison" {
  name                = "f5-biannual-comparison-prod"
  description         = "Trigger F5 comparison twice a year: Jan 1 and July 1 at 11:00 UTC (13:00 Israel time)"
  schedule_expression = "cron(0 11 1 1,7 ? *)"

  tags = {
    Name = "F5 Biannual Comparison Schedule - Production"
  }
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule      = aws_cloudwatch_event_rule.biannual_comparison.name
  target_id = "F5ComparisonLambda"
  arn       = aws_lambda_function.f5_comparison.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.f5_comparison.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.biannual_comparison.arn
}
