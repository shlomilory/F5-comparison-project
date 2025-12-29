# F5 Configuration Comparison - Terraform Deployment

Complete Infrastructure as Code for F5 configuration comparison system with AWS VPN connectivity.

## 🏗️ Architecture

```
Your Home Network (10.100.102.0/24)
├── Desktop (10.100.102.11)
├── F51 (10.100.102.10)
└── F52 (10.100.102.12)
     │
     │ VPN Tunnel (OpenVPN over UDP 1194)
     ▼
AWS VPC (10.0.0.0/16)
├── Public Subnet (10.0.1.0/24)
│   └── VPN Server (EC2 t3.micro)
│       └── Routes traffic between home and AWS
└── Private Subnet (10.0.2.0/24)
    └── Lambda Function
        ├── Connects to F51 & F52 via VPN
        ├── Compares configurations
        ├── Uploads to S3
        └── Sends notification to Teams
```

## 📋 Prerequisites

1. **Terraform installed** (>= 1.0)
   ```bash
   # Install Terraform
   # Windows: choco install terraform
   # macOS: brew install terraform
   # Linux: https://www.terraform.io/downloads
   
   terraform version
   ```

2. **AWS CLI configured**
   ```bash
   aws configure
   # Enter your AWS Access Key ID
   # Enter your AWS Secret Access Key
   # Default region: us-east-1
   # Output format: json
   ```

3. **SSH key pair for VPN server**
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/f5_vpn_server -C "F5 VPN Server"
   ```

4. **SSH key pair for F5 servers** (already have from local testing)

5. **Microsoft Teams webhook URL**
   - Create in Teams: Channel → Connectors → Incoming Webhook

## 🚀 Quick Start

### Step 1: Prepare Lambda Code

```bash
# Navigate to project root
cd /path/to/project

# Create deployment package
zip -r lambda_deployment.zip lambda_function.py
```

### Step 2: Configure Variables

```bash
# Copy example variables
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values
notepad terraform.tfvars  # Windows
nano terraform.tfvars     # Linux/macOS
```

**Required variables in `terraform.tfvars`:**

```hcl
# Your home network
home_network_cidr = "10.100.102.0/24"
f5_server1_ip     = "10.100.102.10"
f5_server2_ip     = "10.100.102.12"

# Teams webhook
teams_webhook_url = "https://outlook.office.com/webhook/YOUR_URL"

# SSH private key (paste content or use file())
ssh_private_key = file("~/.ssh/f5_comparison_key")
```

### Step 3: Deploy Infrastructure

```bash
# Initialize Terraform
terraform init

# Preview changes
terraform plan

# Deploy (takes ~5-10 minutes)
terraform apply

# Type 'yes' when prompted
```

### Step 4: Connect to VPN

After deployment, Terraform outputs VPN connection instructions:

```bash
# Get VPN server IP
terraform output vpn_server_public_ip

# SSH to VPN server
ssh -i ~/.ssh/f5_vpn_server ubuntu@<VPN_SERVER_IP>

# Generate client config (run on VPN server)
cd ~/openvpn-ca
./generate-client-config.sh client1

# Download client config to your desktop
exit
scp -i ~/.ssh/f5_vpn_server ubuntu@<VPN_SERVER_IP>:~/client-configs/client1.ovpn .

# Connect with OpenVPN client
sudo openvpn --config client1.ovpn
```

### Step 5: Test Lambda Function

```bash
# Invoke Lambda manually
aws lambda invoke \
  --function-name f5-config-comparison \
  --region us-east-1 \
  response.json

cat response.json

# View logs
aws logs tail /aws/lambda/f5-config-comparison --follow
```

## 📁 Project Structure

```
terraform/
├── main.tf                 # Main configuration, providers
├── variables.tf            # Input variables
├── outputs.tf              # Output values
├── vpc.tf                  # VPC, subnets, route tables, security groups
├── vpn_server.tf          # VPN server EC2 instance
├── lambda.tf              # Lambda function, IAM, EventBridge
├── s3.tf                  # S3 bucket for reports
├── secrets.tf             # Secrets Manager for credentials
├── sns.tf                 # SNS topic for notifications
├── terraform.tfvars       # Your configuration (git-ignored)
├── terraform.tfvars.example
├── .gitignore
├── README.md
└── scripts/
    └── vpn_server_init.sh # VPN server initialization
```

## 🔧 Configuration Options

### Enable/Disable VPN

```hcl
# In terraform.tfvars
enable_vpn = true   # Deploy with VPN (production-like)
enable_vpn = false  # Deploy without VPN (testing only)
```

### Change Lambda Schedule

```hcl
# Daily at 2 AM UTC
lambda_schedule = "cron(0 2 * * ? *)"

# Every hour
lambda_schedule = "cron(0 * * * ? *)"

# Weekdays at 9 AM UTC
lambda_schedule = "cron(0 9 ? * MON-FRI *)"
```

### Adjust Instance Size

```hcl
# VPN server
vpn_instance_type = "t3.micro"   # ~$7/month
vpn_instance_type = "t3.small"   # ~$15/month (more power)
vpn_instance_type = "t2.micro"   # Free tier eligible
```

## 💰 Cost Estimate

**Monthly costs (us-east-1):**

- VPN Server (t3.micro): ~$7.50
- Lambda (5 invocations/day): ~$0.10
- S3 Storage (100 MB): ~$0.02
- Secrets Manager: ~$0.80
- CloudWatch Logs: ~$0.05
- Data Transfer: ~$0.50
- **Total: ~$9/month**

## 🧪 Testing

### Test VPN Connection

```bash
# From your desktop (after connecting to VPN)
ping 10.0.1.x  # VPN server private IP

# From VPN server
ping 10.100.102.10  # F51
ping 10.100.102.12  # F52
```

### Test Lambda Locally

```bash
# Before deploying, test locally
python test_f5_comparison.py
```

### Test Lambda in AWS

```bash
# Manual invocation
aws lambda invoke \
  --function-name f5-config-comparison \
  response.json

# Check S3 for reports
aws s3 ls s3://f5-config-comparison-reports-<ACCOUNT_ID>/
```

## 🔐 Security Best Practices

1. **Never commit secrets**
   - `terraform.tfvars` is git-ignored
   - Use AWS Secrets Manager for credentials

2. **Rotate SSH keys regularly**
   ```bash
   # Generate new key
   ssh-keygen -t ed25519 -f ~/.ssh/f5_new_key
   
   # Update terraform.tfvars
   ssh_private_key = file("~/.ssh/f5_new_key")
   
   # Apply changes
   terraform apply
   ```

3. **Monitor CloudWatch Logs**
   ```bash
   aws logs tail /aws/lambda/f5-config-comparison --follow
   ```

4. **Enable MFA** on AWS account

5. **Restrict VPN access** to your IP only (done automatically)

## 🧹 Cleanup

### Destroy Infrastructure

```bash
# Preview what will be deleted
terraform plan -destroy

# Destroy all resources
terraform destroy

# Type 'yes' when prompted
```

**WARNING:** This will delete:
- All AWS resources
- S3 bucket and all reports
- Secrets in Secrets Manager
- VPN server
- Lambda function

## 📊 Monitoring

### View Lambda Logs

```bash
# Real-time logs
aws logs tail /aws/lambda/f5-config-comparison --follow

# Recent errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/f5-config-comparison \
  --filter-pattern "ERROR"
```

### Check S3 Reports

```bash
# List all reports
aws s3 ls s3://f5-config-comparison-reports-<ACCOUNT_ID>/ --recursive

# Download latest report
aws s3 cp s3://f5-config-comparison-reports-<ACCOUNT_ID>/comparison_<TIMESTAMP>.zip .
```

### CloudWatch Metrics

```bash
# Lambda invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=f5-config-comparison \
  --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum
```

## 🐛 Troubleshooting

### VPN Won't Connect

```bash
# SSH to VPN server
ssh -i ~/.ssh/f5_vpn_server ubuntu@<VPN_IP>

# Check OpenVPN status
sudo systemctl status openvpn@server

# Check logs
sudo tail -f /var/log/openvpn/openvpn.log

# Restart OpenVPN
sudo systemctl restart openvpn@server
```

### Lambda Can't Reach F5 Servers

```bash
# Check VPN route
aws ec2 describe-route-tables --filters "Name=tag:Name,Values=f5-private-rt"

# Check security groups
aws ec2 describe-security-groups --filters "Name=tag:Name,Values=f5-lambda-sg"

# Test from VPN server
ssh -i ~/.ssh/f5_vpn_server ubuntu@<VPN_IP>
ping 10.100.102.10
ssh vboxuser@10.100.102.10
```

### Lambda Errors

```bash
# View recent errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/f5-config-comparison \
  --filter-pattern "ERROR" \
  --max-items 10

# Get function configuration
aws lambda get-function-configuration \
  --function-name f5-config-comparison
```

## 🔄 Updates

### Update Lambda Code

```bash
# Update lambda_function.py
# Then rebuild package
zip -r lambda_deployment.zip lambda_function.py

# Apply changes
terraform apply
```

### Update Environment Variables

```bash
# Edit terraform.tfvars
# Change f5_server1_ip, f5_server2_ip, etc.

# Apply changes
terraform apply
```

### Update VPN Configuration

```bash
# SSH to VPN server
ssh -i ~/.ssh/f5_vpn_server ubuntu@<VPN_IP>

# Edit config
sudo nano /etc/openvpn/server.conf

# Restart
sudo systemctl restart openvpn@server
```

## 📚 Additional Resources

- [Terraform AWS Provider Docs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [OpenVPN Documentation](https://openvpn.net/community-resources/)
- [AWS VPC Guide](https://docs.aws.amazon.com/vpc/latest/userguide/)

## 🤝 Support

Issues or questions? Create an issue or contact the team.

## 📝 License

Internal use only.
