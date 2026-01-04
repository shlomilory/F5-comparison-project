# ============================================================================
# SECRETS MANAGER - F5 SSH CREDENTIALS
# ============================================================================

resource "aws_secretsmanager_secret" "f5_credentials" {
  name                    = "f5_comparison_production_secrets"
  description             = "SSH credentials for F5 servers - Production"
  recovery_window_in_days = 7

  tags = {
    Name = "F5 SSH Credentials - Production"
  }
}

# Secret value will be populated after deployment with:
# {
#   "username": "f5_infra_comparison",
#   "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
# }
