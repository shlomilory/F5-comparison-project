# F5 Configuration Comparison System

> Automated infrastructure monitoring solution using AWS Lambda, VPN tunneling, and Infrastructure as Code

## 🎯 Project Overview

An enterprise-grade automated system that compares F5 BIG-IP configuration files across multiple servers, detects changes, masks sensitive data, and delivers HTML diff reports via S3 with SNS notifications.

## 🏗️ Architecture Diagram

```
AWS Cloud (VPC 10.0.0.0/16)                    Home Network (10.100.102.0/24)
┌─────────────────────────────────┐            ┌──────────────────────────────┐
│  EventBridge (Daily 2 AM UTC)   │            │                              │
│              ▼                  │            │  ┌────────────────────────┐  │
│  ┌────────────────────────┐     │            │  │  VPN Gateway           │  │
│  │  Lambda Function       │     │  VPN       │  │  10.100.102.14         │  │
│  │  (Private Subnet)      │◄────┼──Tunnel────┼─►│  OpenVPN Server        │  │
│  │  • Paramiko SSH/SFTP   │     │            │  └────────────────────────┘  │
│  │  • Config Comparison   │     │            │              │               │
│  │  • Masking & Diff      │     │            │              ├─SSH──►        │
│  └──┬────┬─────┬──────────┘     │            │  ┌───────────▼────────────┐  │
│     │    │     │                │            │  │  F5-1: 10.100.102.10   │  │
│     ▼    ▼     ▼                │            │  │  (Test VM)             │  │
│ ┌────┐ ┌──┐ ┌────┐              │            │  └────────────────────────┘  │
│ │ S3 │ │SM│ │SNS │              │            │              │               │
│ └────┘ └──┘ └────┘              │            │              ├─SSH──►        │
│                                 │            │  ┌───────────▼────────────┐  │
│ VPC Endpoints (Private Access)  │            │  │  F5-2: 10.100.102.12   │  │
└─────────────────────────────────┘            │  │  (Test VM)             │  │
                                               │  └────────────────────────┘  │
                                               └──────────────────────────────┘
```

## ✨ Key Features

- **🔄 Automated Comparison**: Daily scheduled execution comparing F5 configurations
- **🔒 Security First**: End-to-end encryption, credential masking, VPC isolation
- **🌐 VPN Tunneling**: Site-to-site OpenVPN connecting AWS to on-premise
- **📊 Visual Reports**: HTML diff reports with color-coded changes
- **☁️ Infrastructure as Code**: 100% Terraform-managed AWS infrastructure
- **🔐 Secrets Management**: AWS Secrets Manager for secure credential storage
- **📦 Serverless**: No servers to maintain, pay only for execution time
- **📈 Monitoring**: CloudWatch Logs with detailed execution tracking

## 🛠️ Technology Stack

**AWS Services**: Lambda • VPC • S3 • Secrets Manager • SNS • EventBridge • CloudWatch

**Infrastructure**: Terraform • OpenVPN • Docker

**Languages**: Python 3.11 • HCL (Terraform)

**Libraries**: Paramiko • Boto3 • difflib

## 📋 What This Demonstrates

### DevOps Skills
✅ Infrastructure as Code (Terraform)  
✅ AWS Cloud Architecture  
✅ CI/CD-ready infrastructure  
✅ Version control best practices

### Networking
✅ VPC design and security groups  
✅ Site-to-site VPN configuration  
✅ Complex multi-network routing  
✅ VPC endpoints for private connectivity

### Security
✅ Secrets management  
✅ Data encryption (at rest & in transit)  
✅ Least privilege IAM policies  
✅ Network isolation

### Automation
✅ Python scripting  
✅ SSH/SFTP automation  
✅ Scheduled task execution  
✅ Error handling and logging

## 🚀 Quick Start

### Prerequisites
- AWS Account with SSO
- Terraform v1.14+
- Docker
- Home router with port forwarding

### Deployment

```bash
# 1. Configure variables
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# Edit terraform.tfvars with your settings

# 2. Set SSH key
export TF_VAR_ssh_private_key=$(cat ~/.ssh/your_key)

# 3. Build Lambda package
docker run --rm -v ${PWD}:/var/task --entrypoint pip \
  public.ecr.aws/lambda/python:3.11 install paramiko -t /var/task/python/
zip -r lambda_deployment.zip lambda_function.py python/

# 4. Deploy
cd terraform
terraform init
terraform apply
```

## 💰 Cost Breakdown

| Component | Monthly Cost |
|-----------|--------------|
| Lambda | ~$0.10 |
| VPN Server (t3.micro) | ~$7.50 |
| S3 | ~$0.02 |
| Secrets Manager | ~$0.80 |
| VPC Endpoints | ~$14.40 |
| **Total** | **~$23/month** |

## 📊 Sample Output

The system generates detailed HTML comparison reports showing:
- **Line-by-line diffs** with color coding
- **Added configurations** (green highlight)
- **Removed configurations** (red highlight)
- **Statistics**: Total lines, changes, additions, deletions
- **Masked credentials**: All passwords/keys automatically hidden

Reports are automatically uploaded to S3 and accessible via presigned URLs.

## 🎓 Technical Highlights

### Complex Problem Solving
- Resolved Lambda networking limitations using VPN tunneling
- Implemented cross-platform package building (Windows → Linux Lambda)
- Designed secure credential flow through multiple AWS services

### Production-Ready Features
- Comprehensive error handling with CloudWatch integration
- Lifecycle policies for automatic S3 cleanup
- Modular Terraform configuration for easy maintenance
- Security group rules following least privilege principle

### Real-World Application
- Currently running in production AWS environment
- Successfully compares test F5 configurations daily
- Demonstrates understanding of enterprise networking requirements

## 📝 Project Structure

```
f5-config-comparison/
├── terraform/              # IaC configuration
│   ├── main.tf            # Provider & backend
│   ├── vpc.tf             # Network infrastructure
│   ├── lambda.tf          # Serverless function
│   ├── s3.tf              # Storage
│   ├── secrets.tf         # Credential management
│   ├── iam.tf             # Permissions
│   └── ...
├── lambda_function.py     # Python automation code
├── scripts/               # Helper scripts
└── README.md
```

## 🔐 Security Features

- **Private VPC Deployment**: Lambda has no internet access
- **VPC Endpoints**: Private AWS service connectivity
- **Encryption**: All data encrypted (S3-SSE, Secrets Manager)
- **Credential Masking**: Regex-based sensitive data removal
- **Certificate-Based VPN**: Strong authentication (AES-256-GCM)
- **IAM Least Privilege**: Minimal required permissions only

## 🎯 Future Enhancements

- [ ] Multi-region deployment support
- [ ] Automated testing pipeline (unit + integration tests)
- [ ] CloudWatch Dashboard with metrics
- [ ] Teams/Slack webhook integration
- [ ] Configuration versioning and rollback
- [ ] Support for multiple F5 device pairs

## 📄 License

MIT License

## 👤 Author

Shlomi Lory  
DevOps Engineer | AWS | Terraform | Python

---

💡 **This project demonstrates real-world DevOps skills** including cloud architecture, automation, security, and infrastructure as code.