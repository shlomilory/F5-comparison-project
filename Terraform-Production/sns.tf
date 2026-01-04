# ============================================================================
# SNS TOPIC FOR TEAMS NOTIFICATIONS
# ============================================================================

resource "aws_sns_topic" "f5_comparison" {
  name = "f5-comparison-notifications-prod"

  tags = {
    Name = "F5 Comparison Notifications - Production"
  }
}
