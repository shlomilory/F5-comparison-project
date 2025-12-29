# AWS Secrets Manager - SSH Credentials

resource "aws_secretsmanager_secret" "ssh_credentials" {
  name        = "f5-config-comparison/ssh-credentials"
  description = "SSH credentials for accessing F5 servers"

  tags = merge(local.common_tags, {
    Name = "f5-ssh-credentials"
  })
}

resource "aws_secretsmanager_secret_version" "ssh_credentials" {
  secret_id = aws_secretsmanager_secret.ssh_credentials.id

  secret_string = jsonencode({
    username    = var.f5_ssh_username
    private_key = var.ssh_private_key
  })
}

# Teams Webhook URL
resource "aws_secretsmanager_secret" "teams_webhook" {
  name        = "f5-config-comparison/teams-webhook"
  description = "Microsoft Teams webhook URL for notifications"

  tags = merge(local.common_tags, {
    Name = "f5-teams-webhook"
  })
}

resource "aws_secretsmanager_secret_version" "teams_webhook" {
  secret_id = aws_secretsmanager_secret.teams_webhook.id

  secret_string = jsonencode({
    webhook_url = var.teams_webhook_url
  })
}
