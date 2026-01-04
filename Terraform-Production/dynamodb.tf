# ============================================================================
# DYNAMODB TABLE FOR COMPARISON HISTORY
# ============================================================================

resource "aws_dynamodb_table" "comparison_history" {
  name           = var.dynamodb_table_name
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "comparison_id"
  range_key      = "timestamp"

  attribute {
    name = "comparison_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "F5 Comparison History - Production"
  }
}
