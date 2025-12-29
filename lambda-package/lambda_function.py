"""
AWS Lambda Function: F5 Configuration Comparison Tool
Version: 2.0 - SNS + Teams Webhook

This Lambda function compares configuration files from two servers,
masks sensitive information, and sends notifications to Microsoft Teams via SNS.
"""

import os
import difflib
import zipfile
import logging
import re
import json
from pathlib import Path
from typing import List, Dict, Any
import boto3
from botocore.exceptions import ClientError
import tempfile
from datetime import datetime
import urllib.request
import urllib.parse
import paramiko

# AWS Configuration
s3_client = boto3.client('s3')
sns_client = boto3.client('sns')
secrets_client = boto3.client('secretsmanager')

# Environment variables
BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
SECRET_NAME = os.environ.get('SECRET_NAME')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
TEAMS_WEBHOOK_URL = os.environ.get('TEAMS_WEBHOOK_URL', '')  # Optional: direct Teams webhook

# Logger setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_ssh_credentials() -> Dict[str, str]:
    """
    Retrieve SSH credentials from AWS Secrets Manager
    
    Returns:
        dict: Contains 'username' and 'private_key'
    """
    try:
        response = secrets_client.get_secret_value(SecretId=SECRET_NAME)
        secret = json.loads(response['SecretString'])
        return secret
    except ClientError as e:
        logger.error(f"Error retrieving secret: {e}")
        raise


def setup_ssh_key(private_key_content: str, key_path: str) -> None:
    """
    Write SSH private key to file and set permissions
    
    Args:
        private_key_content: Content of the private key
        key_path: Path where to save the key
    """
    with open(key_path, 'w') as key_file:
        key_file.write(private_key_content)
    os.chmod(key_path, 0o600)
    logger.info(f"SSH key written to {key_path}")


def copy_file_from_remote(
    username: str,
    server: str,
    remote_file_path: str,
    local_file_path: str,
    ssh_key_path: str
) -> List[str]:
    """
    Copy file from remote server using paramiko SFTP with SSH key authentication
    
    Args:
        username: Username for SSH connection
        server: IP address or hostname of remote server
        remote_file_path: Path to file on remote server
        local_file_path: Path to save file locally
        ssh_key_path: Path to SSH private key
        
    Returns:
        List of lines from the copied file
    """
    ssh = None
    sftp = None
    try:
        logger.info(f"Connecting to {server} via SSH")
        
        # Create SSH client
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Load private key
        try:
            # Try Ed25519 key first (what we created)
            private_key = paramiko.Ed25519Key.from_private_key_file(ssh_key_path)
        except:
            # Fallback to RSA if needed
            private_key = paramiko.RSAKey.from_private_key_file(ssh_key_path)
        
        # Connect to server with banner handling
        ssh.connect(
            hostname=server,
            username=username,
            pkey=private_key,
            timeout=60,
            banner_timeout=60,  # Wait for banner to complete
            auth_timeout=60,
            look_for_keys=False,
            allow_agent=False
        )
        
        logger.info(f"Connected to {server}, downloading file via SFTP")
        
        # Open SFTP session
        sftp = ssh.open_sftp()
        
        # Download file
        sftp.get(remote_file_path, local_file_path)
        
        logger.info(f"File copied successfully from {server}")

        # Read the content
        try:
            with open(local_file_path, 'r', encoding='utf-8') as f:
                return f.readlines()
        except UnicodeDecodeError:
            with open(local_file_path, 'r', encoding='latin-1') as f:
                return f.readlines()
                
    except paramiko.SSHException as e:
        logger.error(f"SSH connection failed to {server}: {e}")
        raise RuntimeError(f"Failed to connect to {server}: {e}")
    except FileNotFoundError as e:
        logger.error(f"File not found on {server}: {remote_file_path}")
        raise RuntimeError(f"File not found: {remote_file_path}")
    except Exception as e:
        logger.error(f"Error copying file from {server}: {e}")
        raise RuntimeError(f"Failed to copy file from {server}: {e}")
    finally:
        # Clean up connections
        if sftp:
            sftp.close()
        if ssh:
            ssh.close()


def mask_passwords(file_path: str, content: List[str]) -> None:
    """
    Mask passwords and sensitive information in configuration files
    
    Args:
        file_path: Path to file where masked content will be saved
        content: List of strings containing the file content
    """
    logger.info(f"Masking sensitive information")
    
    sensitive_pattern = r"(\w*pass(?:word|phrase)|\w*secret|\w*key|\w*bind-pw|\w*community|\w*string)(?:\s+|:)([^\s]+)"
    
    masked_content = []
    for line in content:
        masked_line = re.sub(
            sensitive_pattern, 
            lambda x: f"{x.group(1)} {'*' * len(x.group(2))}", 
            line, 
            flags=re.IGNORECASE
        )
        masked_content.append(masked_line)
    
    with open(file_path, 'w', encoding='utf-8') as file:
        file.writelines(masked_content)
    logger.info(f"Successfully masked sensitive data")


def compare_files(
    file1_path: str,
    file2_path: str,
    server1: str,
    server2: str,
    output_html: str
) -> Dict[str, Any]:
    """
    Compare two files and generate HTML diff report
    
    Args:
        file1_path: Path to first file
        file2_path: Path to second file
        server1: Name/IP of first server (for display)
        server2: Name/IP of second server (for display)
        output_html: Path for HTML diff output
        
    Returns:
        Dict with comparison statistics
    """
    logger.info(f"Comparing files from {server1} and {server2}")
    
    # Read files
    with open(file1_path, 'r', encoding='utf-8') as file1:
        content1 = file1.readlines()
    with open(file2_path, 'r', encoding='utf-8') as file2:
        content2 = file2.readlines()
    
    # Calculate differences
    differ = difflib.Differ()
    diff = list(differ.compare(content1, content2))
    
    added_lines = sum(1 for line in diff if line.startswith('+ '))
    removed_lines = sum(1 for line in diff if line.startswith('- '))
    total_changes = added_lines + removed_lines
    
    # Generate HTML diff
    html_differ = difflib.HtmlDiff(tabsize=2)
    html_diff = html_differ.make_table(
        fromlines=content1,
        tolines=content2,
        fromdesc=f"{server1} Configuration",
        todesc=f"{server2} Configuration",
        context=True
    )
    
    css = """
    <style>
    table.diff {
        width: 100%;
        max-width: 100%;
        table-layout: auto;
        font-size: 0.9em;
        word-break: break-word;
    }
    .diff-container {
        overflow-x: auto;
        width: 100%;
    }
    </style>
    """
    
    html_output = f"""<!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>F5 Configuration Diff: {server1} vs {server2}</title>
    {css}
    </head>
    <body>
    <div class="diff-container">
    {html_diff}
    </div>
    </body>
    </html>
    """

    with open(output_html, 'w', encoding='utf-8') as html_file:
        html_file.write(html_output)
    logger.info(f"HTML diff report saved")
    
    return {
        'total_lines_server1': len(content1),
        'total_lines_server2': len(content2),
        'added_lines': added_lines,
        'removed_lines': removed_lines,
        'total_changes': total_changes
    }


def create_zip(html_file: str, zip_path: str) -> str:
    """Create compressed zip file of the HTML report"""
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        zipf.write(html_file, arcname=Path(html_file).name)
    logger.info(f"Compressed report created")
    return zip_path


def upload_to_s3(file_path: str, bucket: str, key: str) -> str:
    """
    Upload file to S3 and return presigned URL
    
    Args:
        file_path: Local file path to upload
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        Presigned URL for the uploaded file
    """
    try:
        s3_client.upload_file(file_path, bucket, key)
        logger.info(f"Uploaded {key} to S3 bucket {bucket}")
        
        # Generate presigned URL (valid for 7 days)
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=604800  # 7 days
        )
        return url
    except ClientError as e:
        logger.error(f"Error uploading to S3: {e}")
        raise


def create_teams_card(
    server1: str,
    server2: str,
    stats: Dict[str, Any],
    s3_url: str,
    timestamp: str,
    status: str = "success"
) -> Dict[str, Any]:
    """
    Create Microsoft Teams Adaptive Card message
    
    Args:
        server1: First server IP/name
        server2: Second server IP/name
        stats: Comparison statistics
        s3_url: URL to download report
        timestamp: Execution timestamp
        status: Status of comparison (success/error)
        
    Returns:
        Teams webhook payload
    """
    # Determine color based on status and changes
    if status == "error":
        theme_color = "FF0000"  # Red
        title = "❌ F5 Configuration Comparison Failed"
    elif stats.get('total_changes', 0) == 0:
        theme_color = "00FF00"  # Green
        title = "✅ F5 Configuration Comparison - No Changes"
    else:
        theme_color = "FFA500"  # Orange
        title = f"⚠️ F5 Configuration Comparison - {stats.get('total_changes', 0)} Changes Detected"
    
    # Create adaptive card
    card = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": theme_color,
        "summary": title,
        "sections": [
            {
                "activityTitle": title,
                "activitySubtitle": f"Comparison Date: {timestamp}",
                "facts": [
                    {
                        "name": "Server 1:",
                        "value": server1
                    },
                    {
                        "name": "Server 2:",
                        "value": server2
                    },
                    {
                        "name": "Total Lines (Server 1):",
                        "value": str(stats.get('total_lines_server1', 'N/A'))
                    },
                    {
                        "name": "Total Lines (Server 2):",
                        "value": str(stats.get('total_lines_server2', 'N/A'))
                    },
                    {
                        "name": "Added Lines:",
                        "value": str(stats.get('added_lines', 'N/A'))
                    },
                    {
                        "name": "Removed Lines:",
                        "value": str(stats.get('removed_lines', 'N/A'))
                    },
                    {
                        "name": "Total Changes:",
                        "value": str(stats.get('total_changes', 'N/A'))
                    }
                ],
                "markdown": True
            }
        ],
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "Download Comparison Report",
                "targets": [
                    {
                        "os": "default",
                        "uri": s3_url
                    }
                ]
            }
        ]
    }
    
    return card


def send_teams_notification_direct(webhook_url: str, card: Dict[str, Any]) -> None:
    """
    Send notification directly to Teams webhook
    
    Args:
        webhook_url: Teams webhook URL
        card: Teams message card
    """
    try:
        data = json.dumps(card).encode('utf-8')
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req) as response:
            result = response.read()
            logger.info(f"Teams notification sent successfully: {result.decode('utf-8')}")
            
    except Exception as e:
        logger.error(f"Error sending Teams notification: {e}")
        raise


def send_notification_sns(
    topic_arn: str,
    server1: str,
    server2: str,
    stats: Dict[str, Any],
    s3_url: str,
    timestamp: str,
    status: str = "success"
) -> None:
    """
    Send notification via SNS (which can trigger Teams webhook via Lambda subscription)
    
    Args:
        topic_arn: SNS topic ARN
        server1: First server IP/name
        server2: Second server IP/name
        stats: Comparison statistics
        s3_url: URL to download report
        timestamp: Execution timestamp
        status: Status of comparison
    """
    logger.info(f"Sending SNS notification to {topic_arn}")
    
    try:
        # Create message
        subject = f"F5 Config Comparison: {server1} vs {server2}"
        
        message = {
            "server1": server1,
            "server2": server2,
            "timestamp": timestamp,
            "status": status,
            "statistics": stats,
            "report_url": s3_url
        }
        
        # Send to SNS
        response = sns_client.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=json.dumps(message, indent=2),
            MessageAttributes={
                'event_type': {
                    'DataType': 'String',
                    'StringValue': 'f5_comparison'
                },
                'status': {
                    'DataType': 'String',
                    'StringValue': status
                }
            }
        )
        
        logger.info(f"SNS message published successfully. MessageId: {response['MessageId']}")
        
    except ClientError as e:
        logger.error(f"Error sending SNS notification: {e}")
        raise


def lambda_handler(event, context):
    """
    AWS Lambda handler function
    
    Args:
        event: Lambda event object (can contain server IPs, etc.)
        context: Lambda context object
        
    Returns:
        dict: Response with status and message
    """
    logger.info("Starting F5 configuration comparison")
    logger.info(f"Event: {json.dumps(event)}")
    
    # Get configuration from event or use defaults
    server1 = event.get('server1', os.environ.get('SERVER1', '192.168.1.10'))
    server2 = event.get('server2', os.environ.get('SERVER2', '192.168.1.11'))
    config_path = event.get('config_path', os.environ.get('CONFIG_PATH', '/home/ubuntu/bigip.conf'))
    
    # Create temporary directory for file operations
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Get SSH credentials from Secrets Manager
            credentials = get_ssh_credentials()
            username = credentials['username']
            private_key = credentials['private_key']
            
            # Setup SSH key
            ssh_key_path = os.path.join(temp_dir, 'id_rsa')
            setup_ssh_key(private_key, ssh_key_path)
            
            # Define file paths
            local_file1 = os.path.join(temp_dir, f'{server1}_config.txt')
            local_file2 = os.path.join(temp_dir, f'{server2}_config.txt')
            html_file = os.path.join(temp_dir, 'comparison.html')
            zip_file = os.path.join(temp_dir, 'comparison.zip')
            
            # Copy files from remote servers
            logger.info(f"Copying configuration from {server1}")
            content1 = copy_file_from_remote(
                username, server1, config_path, local_file1, ssh_key_path
            )
            
            logger.info(f"Copying configuration from {server2}")
            content2 = copy_file_from_remote(
                username, server2, config_path, local_file2, ssh_key_path
            )
            
            # Mask sensitive information
            mask_passwords(local_file1, content1)
            mask_passwords(local_file2, content2)
            
            # Compare files and get statistics
            stats = compare_files(local_file1, local_file2, server1, server2, html_file)
            
            # Create zip
            create_zip(html_file, zip_file)
            
            # Upload to S3
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            s3_key = f"comparisons/{timestamp}_comparison.zip"
            s3_url = upload_to_s3(zip_file, BUCKET_NAME, s3_key)
            
            # Create Teams card
            teams_card = create_teams_card(
                server1, server2, stats, s3_url, 
                datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
                "success"
            )
            
            # Send notifications
            # Option 1: Direct Teams webhook (if provided)
            if TEAMS_WEBHOOK_URL:
                send_teams_notification_direct(TEAMS_WEBHOOK_URL, teams_card)
            
            # Option 2: SNS (can trigger Teams via another Lambda)
            if SNS_TOPIC_ARN:
                send_notification_sns(
                    SNS_TOPIC_ARN,
                    server1,
                    server2,
                    stats,
                    s3_url,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
                    "success"
                )
            
            logger.info("Configuration comparison completed successfully")
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Configuration comparison completed successfully',
                    'servers': [server1, server2],
                    's3_url': s3_url,
                    'timestamp': timestamp,
                    'statistics': stats
                })
            }
            
        except Exception as e:
            logger.error(f"Error in lambda handler: {e}", exc_info=True)
            
            # Send error notification
            error_stats = {'error': str(e)}
            error_card = create_teams_card(
                server1, server2, error_stats, '', 
                datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'),
                "error"
            )
            
            try:
                if TEAMS_WEBHOOK_URL:
                    send_teams_notification_direct(TEAMS_WEBHOOK_URL, error_card)
            except:
                pass
            
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'message': 'Error during configuration comparison',
                    'error': str(e)
                })
            }