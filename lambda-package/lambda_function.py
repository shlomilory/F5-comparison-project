"""
AWS Lambda Function: F5 Configuration Comparison Tool
Version: 5.3.1 - Site-Aware + Universal Ignore Rules + Environment-Appropriate Severity

🎉 New Features in v5.3.1 - SANDBOX/CORP IP DOWNGRADE:
- IP differences in SANDBOX/CORP are now WARNING instead of CRITICAL
- Only PROD has CRITICAL IP differences
- SANDBOX and CORP are testing environments - even major differences are warnings

Severity by Environment:
📍 PROD:
  🔴 CRITICAL: Same-network different hosts, completely different networks, missing configs
  ⚠️ WARNING: Other non-IP differences
  ✅ MATCH: Cross-site IPs, timestamps

📍 CORP / SANDBOX:
  ⚠️ WARNING: All IP differences, missing configs, other differences
  ✅ MATCH: Cross-site IPs (when same host), timestamps

📍 ALL Environments - Always Ignored:
  ✅ Cross-site different hosts (10.100.x.x vs 10.200.y.y)
  ✅ Timestamps (creation-time, last-modified-time)

Features in v5.3.0:
- Cross-site different hosts ignored in ALL environments
- Timestamp differences ignored in ALL environments

Features in v5.2:
- New risk scoring: <critical>/<total> with percentages
- Risk levels: LOW (<1%), MEDIUM (1-5%), HIGH (>5%)

Previous Features:
- Site-aware IP comparison
- Environment-based risk classification
- Redundancy detection
- Default collapsed UI
"""

import os
import zipfile
import logging
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
import boto3
from botocore.exceptions import ClientError
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
import paramiko

# AWS Clients
s3_client = boto3.client('s3')
sns_client = boto3.client('sns')
secrets_client = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')

# Environment variables
BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')
SECRET_NAME = os.environ.get('SECRET_NAME')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE_NAME', 'f5-comparison-history')
TEAMS_WEBHOOK_URL = os.environ.get('TEAMS_WEBHOOK_URL', '')

# Logger setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# DynamoDB table
comparison_table = dynamodb.Table(DYNAMODB_TABLE)


def get_ssh_credentials() -> Dict[str, str]:
    """Retrieve SSH credentials from AWS Secrets Manager"""
    try:
        response = secrets_client.get_secret_value(SecretId=SECRET_NAME)
        secret = json.loads(response['SecretString'])
        return secret
    except ClientError as e:
        logger.error(f"Error retrieving credentials: {e}")
        raise


def copy_file_from_remote(
    host: str,
    username: str,
    private_key_path: str,
    remote_path: str,
    local_path: str
) -> None:
    """Copy file from remote server via SSH/SFTP with proper cleanup"""
    transport = None
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        logger.info(f"Connecting to {host} via SSH")
        ssh.connect(
            hostname=host,
            username=username,
            key_filename=private_key_path,
            timeout=30,
            auth_timeout=30,
            banner_timeout=30
        )
        
        # Get transport BEFORE opening SFTP (critical for cleanup!)
        transport = ssh.get_transport()
        
        logger.info(f"Connected to {host}, downloading file via SFTP")
        sftp = ssh.open_sftp()
        
        try:
            sftp.get(remote_path, local_path)
            logger.info(f"File copied successfully from {host}")
        finally:
            sftp.close()
            
    finally:
        ssh.close()
        # Close transport explicitly to stop background threads
        if transport:
            transport.close()


def mask_sensitive_data(content: str) -> str:
    """Mask sensitive information in configuration"""
    logger.info("Masking sensitive information")
    
    patterns = {
        r'password\s+\S+': 'password ********',
        r'secret\s+\S+': 'secret ********',
        r'key\s+\S+': 'key ********',
        r'cert\s+\S+': 'cert ********',
    }
    
    masked_content = content
    for pattern, replacement in patterns.items():
        masked_content = re.sub(pattern, replacement, masked_content, flags=re.IGNORECASE)
    
    logger.info("Successfully masked sensitive data")
    return masked_content


def parse_ltm_virtual_servers(content: str) -> Dict[str, Dict[str, str]]:
    """Parse LTM virtual server configurations from F5 config file"""
    virtual_servers = {}
    
    vs_pattern = r'ltm virtual ([^\s{]+)\s*\{'
    matches = re.finditer(vs_pattern, content)
    
    for match in matches:
        vs_name = match.group(1)
        start_pos = match.start()
        
        brace_count = 0
        in_vs_block = False
        block_start = 0
        
        for i in range(start_pos, len(content)):
            if content[i] == '{':
                if not in_vs_block:
                    in_vs_block = True
                    block_start = i + 1
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0 and in_vs_block:
                    block_end = i
                    block_content = content[block_start:block_end]
                    config = parse_config_block(block_content)
                    virtual_servers[vs_name] = config
                    break
    
    return virtual_servers


def parse_config_block(block_content: str) -> Dict[str, str]:
    """Parse configuration block into key-value pairs"""
    config = {}
    lines = [line.strip() for line in block_content.strip().split('\n')]
    
    block = []
    brace_count = 0
    
    for line in lines:
        for char in line:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
        
        if brace_count == 0:
            block.append(line)
    
    for line in block:
        if not line or line in ['{', '}']:
            continue
        
        if ' ' in line:
            parts = line.split(None, 1)
            if len(parts) == 2:
                key, value = parts
                config[key] = value.strip()
            elif len(parts) == 1:
                config[parts[0]] = '{'
    
    return config


def normalize_site_ip(ip_str: str) -> Tuple[str, str]:
    """
    Normalize site-specific IPs for comparison
    Returns: (normalized_ip, site_identifier)
    
    Examples:
        10.100.50.10:443 -> (SITE.50.10:443, 'NJ')
        10.200.50.10:443 -> (SITE.50.10:443, 'HRZ')
        192.168.1.1:80   -> (192.168.1.1:80, 'OTHER')
    """
    # Extract IP pattern
    nj_pattern = r'10\.100\.(\d+\.\d+)'
    hrz_pattern = r'10\.200\.(\d+\.\d+)'
    
    nj_match = re.search(nj_pattern, ip_str)
    hrz_match = re.search(hrz_pattern, ip_str)
    
    if nj_match:
        host_part = nj_match.group(1)
        normalized = re.sub(nj_pattern, f'SITE.{host_part}', ip_str)
        return (normalized, 'NJ')
    elif hrz_match:
        host_part = hrz_match.group(1)
        normalized = re.sub(hrz_pattern, f'SITE.{host_part}', ip_str)
        return (normalized, 'HRZ')
    else:
        return (ip_str, 'OTHER')


def classify_ip_difference(ip1: str, ip2: str) -> Tuple[bool, str]:
    """
    Classify IP difference severity
    Returns: (is_different, severity_level)
    
    Severity levels:
    - 'MATCH': Same host across sites (10.100.221.169 vs 10.200.221.169)
    - 'WARNING': Cross-site different hosts (10.100.221.169 vs 10.200.221.187)
    - 'CRITICAL': Same-network different hosts (10.100.221.169 vs 10.100.221.200) OR completely different networks
    """
    norm1, site1 = normalize_site_ip(ip1)
    norm2, site2 = normalize_site_ip(ip2)
    
    # If normalized IPs match, they're the same host across sites → MATCH
    if norm1 == norm2:
        return (False, 'MATCH')
    
    # Both are site IPs
    if site1 in ['NJ', 'HRZ'] and site2 in ['NJ', 'HRZ']:
        # CRITICAL: Same network, different hosts (both NJ OR both HRZ)
        if site1 == site2:
            return (True, 'CRITICAL')
        # WARNING: Cross-site, different hosts (NJ vs HRZ)
        else:
            return (True, 'WARNING')
    
    # CRITICAL: Completely different networks (e.g., 10.100.x.x vs 192.168.x.x)
    return (True, 'CRITICAL')


def get_environment_type(vs_name: str) -> str:
    """
    Determine environment type from virtual server name
    Returns: 'PROD', 'CORP', 'SANDBOX', or 'UNKNOWN'
    """
    name_lower = vs_name.lower()
    
    if name_lower.startswith('prod'):
        return 'PROD'
    elif name_lower.startswith('corp') or name_lower.startswith('crp'):
        return 'CORP'
    elif name_lower.startswith('sb'):
        return 'SANDBOX'
    else:
        return 'UNKNOWN'


def compare_virtual_servers(
    vs1: Dict[str, Dict[str, str]],
    vs2: Dict[str, Dict[str, str]]
) -> List[Dict[str, Any]]:
    """Compare virtual servers between two F5 configs with site-aware logic"""
    comparison_data = []
    
    all_vs_names = set(vs1.keys()) | set(vs2.keys())
    
    for vs_name in sorted(all_vs_names):
        short_name = vs_name.split('/')[-1]
        env_type = get_environment_type(short_name)
        
        vs_config1 = vs1.get(vs_name, {})
        vs_config2 = vs2.get(vs_name, {})
        
        # Check for missing redundancy
        missing_in_file1 = len(vs_config1) == 0
        missing_in_file2 = len(vs_config2) == 0
        has_no_redundancy = missing_in_file1 or missing_in_file2
        
        all_keys = set(vs_config1.keys()) | set(vs_config2.keys())
        
        configurations = []
        has_differences = False
        is_critical = False
        is_warning = False
        
        for key in sorted(all_keys):
            value1 = vs_config1.get(key, '(missing)')
            value2 = vs_config2.get(key, '(missing)')
            
            # Special case: Ignore ALL timestamp metadata in ALL environments (always OK!)
            # Timestamps are metadata and expected to differ between sites
            # They don't affect F5 functionality and should never be flagged
            if key in ['last-modified-time', 'creation-time']:
                # Always ignore - whether missing OR different, in ANY environment
                configurations.append({
                    'key': key,
                    'file1': value1,
                    'file2': value2,
                    'isDiff': False,  # Never mark as difference
                    'isIP': False,
                    'severity': 'MATCH'
                })
                continue
            
            # Check if this is a destination IP
            is_destination = 'destination' in key.lower()
            
            if is_destination and value1 != '(missing)' and value2 != '(missing)':
                # Site-aware IP comparison
                is_diff, severity = classify_ip_difference(value1, value2)
                
                # Special case for ALL environments: Ignore cross-site different hosts (expected!)
                # Cross-site architecture is standard across PROD, CORP, and SANDBOX
                if severity == 'WARNING':
                    # Cross-site different hosts → Not even a warning, just MATCH!
                    is_diff = False
                    severity = 'MATCH'
                
                # Downgrade CRITICAL to WARNING for non-PROD environments
                # SANDBOX and CORP are for testing - even major IP differences are just warnings
                if severity == 'CRITICAL' and env_type in ['CORP', 'SANDBOX', 'UNKNOWN']:
                    severity = 'WARNING'
                
                if severity == 'MATCH':
                    # Same host across sites - not a difference!
                    is_diff = False
                elif severity == 'WARNING':
                    is_diff = True
                    is_warning = True
                    has_differences = True
                elif severity == 'CRITICAL':
                    is_diff = True
                    is_critical = True
                    has_differences = True
                
                configurations.append({
                    'key': key,
                    'file1': value1,
                    'file2': value2,
                    'isDiff': is_diff,
                    'isIP': True,
                    'severity': severity if is_diff else 'MATCH'
                })
            else:
                # Non-IP comparison (original logic)
                is_diff = value1 != value2
                is_ip = is_ip_address(value1) or is_ip_address(value2)
                
                if is_diff:
                    has_differences = True
                    
                    # CRITICAL in PROD only if (missing) - i.e., mismatch
                    if env_type == 'PROD' and (value1 == '(missing)' or value2 == '(missing)'):
                        is_critical = True
                    # WARNING for PROD if both values exist but are different
                    elif env_type == 'PROD':
                        is_warning = True
                    # WARNING for CORP/SANDBOX
                    elif env_type in ['CORP', 'SANDBOX']:
                        is_warning = True
                
                configurations.append({
                    'key': key,
                    'file1': value1,
                    'file2': value2,
                    'isDiff': is_diff,
                    'isIP': is_ip,
                    'severity': 'CRITICAL' if (is_diff and env_type == 'PROD' and (value1 == '(missing)' or value2 == '(missing)')) else ('WARNING' if is_diff else 'MATCH')
                })
        
        # Final classification logic
        if has_no_redundancy and env_type in ['CORP', 'SANDBOX']:
            is_warning = True
            is_critical = False
        
        # Badge determination
        badge_type = 'CRITICAL' if is_critical else ('WARNING' if (is_warning or has_no_redundancy) else 'MATCH')
        
        comparison_data.append({
            'name': short_name,
            'path': vs_name,
            'environment': env_type,
            'hasDifferences': has_differences,
            'isCritical': is_critical,
            'isWarning': is_warning,
            'hasNoRedundancy': has_no_redundancy,
            'missingInFile1': missing_in_file1,
            'missingInFile2': missing_in_file2,
            'badgeType': badge_type,
            'configurations': configurations
        })
    
    return comparison_data


def is_ip_address(value: str) -> bool:
    """Check if a value contains an IP address"""
    ip_pattern = r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'
    return bool(re.search(ip_pattern, value))


def analyze_patterns(comparison_data: List[Dict[str, Any]], historical_data: List[Dict] = None) -> Dict[str, Any]:
    """
    Smart Rules Engine - Analyze patterns with new ratio-based risk scoring
    Risk Score Format: <critical_count>/<total_vs> (percentage)
    """
    insights = {
        'alerts': [],
        'warnings': [],
        'info': [],
        'critical_count': 0,
        'warning_count': 0,
        'match_count': 0,
        'total_count': 0,
        'critical_percentage': 0.0,
        'warning_percentage': 0.0,
        'match_percentage': 0.0,
        'risk_level': 'LOW'  # LOW, MEDIUM, HIGH
    }
    
    total_vs = len(comparison_data)
    critical = sum(1 for vs in comparison_data if vs['isCritical'])
    warnings = sum(1 for vs in comparison_data if vs['isWarning'])
    matches = total_vs - critical - warnings
    no_redundancy = sum(1 for vs in comparison_data if vs['hasNoRedundancy'])
    
    # Calculate percentages
    critical_pct = (critical / total_vs * 100) if total_vs > 0 else 0
    warning_pct = (warnings / total_vs * 100) if total_vs > 0 else 0
    match_pct = (matches / total_vs * 100) if total_vs > 0 else 0
    
    # Store counts and percentages
    insights['critical_count'] = critical
    insights['warning_count'] = warnings
    insights['match_count'] = matches
    insights['total_count'] = total_vs
    insights['critical_percentage'] = round(critical_pct, 1)
    insights['warning_percentage'] = round(warning_pct, 1)
    insights['match_percentage'] = round(match_pct, 1)
    
    # Determine risk level based on critical percentage
    if critical_pct >= 5.0:
        insights['risk_level'] = 'HIGH'
        insights['assessment'] = 'HIGH RISK - Significant critical issues detected'
    elif critical_pct >= 1.0:
        insights['risk_level'] = 'MEDIUM'
        insights['assessment'] = 'MEDIUM RISK - Some critical issues require attention'
    else:
        insights['risk_level'] = 'LOW'
        insights['assessment'] = 'LOW RISK - Minimal critical issues'
    
    # Production virtual servers analysis
    prod_vs = [vs for vs in comparison_data if vs['environment'] == 'PROD']
    prod_critical = sum(1 for vs in prod_vs if vs['isCritical'])
    prod_warnings = sum(1 for vs in prod_vs if vs['isWarning'])
    
    # Rule 1: Critical issues detected
    if critical > 0:
        insights['alerts'].append({
            'type': 'CRITICAL_ISSUES',
            'message': f'🔴 {critical} virtual servers have critical issues ({critical_pct:.1f}%)',
            'severity': 'HIGH'
        })
    
    # Rule 2: Production critical issues (HIGH PRIORITY)
    if prod_critical > 0:
        insights['alerts'].append({
            'type': 'PROD_CRITICAL',
            'message': f'🚨 {prod_critical} PRODUCTION virtual servers have critical issues',
            'severity': 'HIGH'
        })
    
    # Rule 3: Production warnings
    if prod_warnings > 0:
        insights['warnings'].append({
            'type': 'PROD_WARNINGS',
            'message': f'⚠️ {prod_warnings} production virtual servers have warnings',
            'severity': 'MEDIUM'
        })
    
    # Rule 4: Missing redundancy
    if no_redundancy > 0:
        redundancy_pct = (no_redundancy / total_vs * 100) if total_vs > 0 else 0
        insights['warnings'].append({
            'type': 'NO_REDUNDANCY',
            'message': f'⚠️ {no_redundancy} virtual servers exist in only one site ({redundancy_pct:.1f}% - no redundancy)',
            'severity': 'MEDIUM'
        })
    
    # Rule 5: Overall warnings
    if warnings > 0:
        insights['warnings'].append({
            'type': 'WARNINGS_DETECTED',
            'message': f'⚠️ {warnings} virtual servers have warnings ({warning_pct:.1f}%)',
            'severity': 'MEDIUM'
        })
    
    # Rule 6: Environment distribution
    env_counts = {}
    for vs in comparison_data:
        env = vs['environment']
        env_counts[env] = env_counts.get(env, 0) + 1
    
    insights['info'].append({
        'type': 'ENVIRONMENT_DISTRIBUTION',
        'message': f"Environment distribution: {', '.join([f'{env}: {count}' for env, count in env_counts.items()])}",
        'severity': 'INFO'
    })
    
    # Rule 7: Good news if mostly matches
    if match_pct >= 95.0:
        insights['info'].append({
            'type': 'MOSTLY_MATCHES',
            'message': f'✅ {matches} virtual servers match perfectly ({match_pct:.1f}%)',
            'severity': 'INFO'
        })
    
    return insights


def store_comparison_metadata(
    server1: str,
    server2: str,
    comparison_data: List[Dict[str, Any]],
    insights: Dict[str, Any],
    s3_url: str,
    timestamp: str
) -> None:
    """Store comparison metadata in DynamoDB"""
    try:
        comparison_id = f"{server1}_vs_{server2}"
        
        # Store parent comparison record
        comparison_table.put_item(
            Item={
                'comparison_id': comparison_id,
                'timestamp': timestamp,
                'server1': server1,
                'server2': server2,
                's3_url': s3_url,
                'total_vs': len(comparison_data),
                'with_differences': sum(1 for vs in comparison_data if vs['hasDifferences']),
                'critical_count': insights['critical_count'],
                'warning_count': insights['warning_count'],
                'match_count': insights['match_count'],
                'no_redundancy_count': sum(1 for vs in comparison_data if vs['hasNoRedundancy']),
                'critical_percentage': Decimal(str(insights['critical_percentage'])),
                'warning_percentage': Decimal(str(insights['warning_percentage'])),
                'match_percentage': Decimal(str(insights['match_percentage'])),
                'risk_level': insights['risk_level'],
                'assessment': insights['assessment'],
                'ttl': int((datetime.now() + timedelta(days=90)).timestamp())
            }
        )
        
        logger.info(f"Stored comparison metadata in DynamoDB: {comparison_id}")
        
    except ClientError as e:
        logger.error(f"Error storing in DynamoDB: {e}")


def publish_cloudwatch_metrics(
    comparison_data: List[Dict[str, Any]],
    insights: Dict[str, Any]
) -> None:
    """Publish custom metrics to CloudWatch"""
    try:
        # Create a FRESH CloudWatch client (important for VPC endpoints!)
        cw_client = boto3.client('cloudwatch')
        
        cw_client.put_metric_data(
            Namespace='F5/ConfigComparison',
            MetricData=[
                {
                    'MetricName': 'TotalVirtualServers',
                    'Value': insights['total_count'],
                    'Unit': 'Count',
                    'Timestamp': datetime.now()
                },
                {
                    'MetricName': 'CriticalCount',
                    'Value': insights['critical_count'],
                    'Unit': 'Count',
                    'Timestamp': datetime.now()
                },
                {
                    'MetricName': 'WarningCount',
                    'Value': insights['warning_count'],
                    'Unit': 'Count',
                    'Timestamp': datetime.now()
                },
                {
                    'MetricName': 'MatchCount',
                    'Value': insights['match_count'],
                    'Unit': 'Count',
                    'Timestamp': datetime.now()
                },
                {
                    'MetricName': 'CriticalPercentage',
                    'Value': insights['critical_percentage'],
                    'Unit': 'Percent',
                    'Timestamp': datetime.now()
                }
            ]
        )
        
        logger.info("Published metrics to CloudWatch")
        
    except ClientError as e:
        logger.error(f"Error publishing CloudWatch metrics: {e}")
        pass


def generate_enhanced_html(
    comparison_data: List[Dict[str, Any]],
    server1: str,
    server2: str,
    timestamp: str,
    insights: Dict[str, Any]
) -> str:
    """Generate enhanced HTML report with site-aware comparison"""
    
    # Use insights data for stats
    stats = {
        'total': insights['total_count'],
        'critical': insights['critical_count'],
        'warnings': insights['warning_count'],
        'matches': insights['match_count'],
        'critical_pct': insights['critical_percentage'],
        'warning_pct': insights['warning_percentage'],
        'match_pct': insights['match_percentage'],
        'no_redundancy': sum(1 for vs in comparison_data if vs['hasNoRedundancy'])
    }
    
    # Escape data for JavaScript
    comparison_json = json.dumps(comparison_data)
    insights_json = json.dumps(insights)
    
    html_template = f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>F5 LTM Configuration Comparison - Site-Aware Analysis</title>
    <style>
        :root {{
            --bg-primary: #ffffff;
            --bg-secondary: #f5f7fa;
            --bg-card: #ffffff;
            --text-primary: #2c3e50;
            --text-secondary: #7f8c8d;
            --border-color: #e1e8ed;
            --accent-primary: #3498db;
            --accent-success: #27ae60;
            --accent-warning: #f39c12;
            --accent-danger: #e74c3c;
            --shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        [data-theme="dark"] {{
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --bg-card: #0f3460;
            --text-primary: #eee;
            --text-secondary: #bbb;
            --border-color: #2a2a4e;
            --shadow: 0 2px 8px rgba(0,0,0,0.3);
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            transition: background-color 0.3s, color 0.3s;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            box-shadow: var(--shadow);
        }}

        .header h1 {{
            font-size: 2rem;
            margin-bottom: 0.5rem;
        }}

        .header-meta {{
            display: flex;
            gap: 2rem;
            flex-wrap: wrap;
            margin-top: 1rem;
            font-size: 0.95rem;
            opacity: 0.95;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }}

        .controls {{
            background: var(--bg-card);
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: var(--shadow);
            margin-bottom: 2rem;
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
            align-items: center;
        }}

        .search-box {{
            flex: 1;
            min-width: 250px;
            position: relative;
        }}

        .search-box input {{
            width: 100%;
            padding: 0.75rem 1rem 0.75rem 2.5rem;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            font-size: 1rem;
            background: var(--bg-secondary);
            color: var(--text-primary);
            transition: border-color 0.3s;
        }}

        .search-box input:focus {{
            outline: none;
            border-color: var(--accent-primary);
        }}

        .search-icon {{
            position: absolute;
            left: 0.75rem;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-secondary);
        }}

        .filter-buttons {{
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }}

        .filter-btn {{
            padding: 0.75rem 1.25rem;
            border: 2px solid var(--border-color);
            background: var(--bg-secondary);
            color: var(--text-primary);
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.95rem;
            font-weight: 500;
            transition: all 0.3s;
        }}

        .filter-btn:hover {{
            background: var(--accent-primary);
            color: white;
            border-color: var(--accent-primary);
        }}

        .filter-btn.active {{
            background: var(--accent-primary);
            color: white;
            border-color: var(--accent-primary);
        }}

        .theme-toggle {{
            padding: 0.75rem 1.25rem;
            border: 2px solid var(--border-color);
            background: var(--bg-secondary);
            color: var(--text-primary);
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.95rem;
            transition: all 0.3s;
        }}

        .theme-toggle:hover {{
            background: var(--accent-primary);
            color: white;
            border-color: var(--accent-primary);
        }}

        .export-btn {{
            padding: 0.75rem 1.25rem;
            background: var(--accent-success);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.95rem;
            font-weight: 500;
            transition: transform 0.2s;
        }}

        .export-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(39, 174, 96, 0.3);
        }}

        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .stat-card {{
            background: var(--bg-card);
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: var(--shadow);
            text-align: center;
            transition: transform 0.3s;
        }}

        .stat-card:hover {{
            transform: translateY(-4px);
        }}

        .stat-value {{
            font-size: 2.5rem;
            font-weight: bold;
            margin-bottom: 0.5rem;
        }}

        .stat-label {{
            color: var(--text-secondary);
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .stat-card.total .stat-value {{ color: var(--accent-primary); }}
        .stat-card.critical .stat-value {{ color: var(--accent-danger); }}
        .stat-card.warnings .stat-value {{ color: #ff9800; }}
        .stat-card.matches .stat-value {{ color: var(--accent-success); }}
        .stat-card.no-redundancy .stat-value {{ color: #9c27b0; }}

        .insights-panel {{
            background: var(--bg-card);
            padding: 1.5rem;
            border-radius: 12px;
            box-shadow: var(--shadow);
            margin-bottom: 2rem;
        }}

        .insights-header {{
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid var(--border-color);
        }}

        .insights-title {{
            font-size: 1.5rem;
            font-weight: 600;
        }}

        .risk-badge {{
            padding: 0.5rem 1rem;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.9rem;
        }}

        .risk-low {{ background: #d4edda; color: #155724; }}
        .risk-medium {{ background: #fff3cd; color: #856404; }}
        .risk-high {{ background: #f8d7da; color: #721c24; }}

        .insights-grid {{
            display: grid;
            gap: 1rem;
        }}

        .insight-section {{
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid;
        }}

        .insight-section.alerts {{
            background: #fff5f5;
            border-color: #e74c3c;
        }}

        .insight-section.warnings {{
            background: #fffbf0;
            border-color: #f39c12;
        }}

        .insight-section.info {{
            background: #f0f8ff;
            border-color: #3498db;
        }}

        [data-theme="dark"] .insight-section.alerts {{
            background: #2d1f1f;
        }}

        [data-theme="dark"] .insight-section.warnings {{
            background: #2d2a1f;
        }}

        [data-theme="dark"] .insight-section.info {{
            background: #1f2a2d;
        }}

        .insight-title {{
            font-weight: 600;
            margin-bottom: 0.5rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .insight-message {{
            color: var(--text-secondary);
            font-size: 0.95rem;
        }}

        .empty-insights {{
            text-align: center;
            padding: 2rem;
            color: var(--text-secondary);
            font-size: 1.1rem;
        }}

        .virtual-server {{
            background: var(--bg-card);
            border-radius: 12px;
            box-shadow: var(--shadow);
            margin-bottom: 1.5rem;
            overflow: hidden;
            transition: all 0.3s;
        }}

        .virtual-server.collapsed .vs-content {{
            display: none;
        }}

        .virtual-server.collapsed .collapse-icon {{
            transform: rotate(-90deg);
        }}

        .virtual-server.hidden {{
            display: none;
        }}

        .vs-header {{
            padding: 1.25rem 1.5rem;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background-color 0.3s;
        }}

        .vs-header:hover {{
            background: var(--bg-secondary);
        }}

        .vs-header.has-diff {{
            border-left: 4px solid var(--accent-warning);
        }}

        .vs-header.no-diff {{
            border-left: 4px solid var(--accent-success);
        }}

        .vs-title {{
            display: flex;
            align-items: center;
            gap: 1rem;
            font-weight: 600;
            font-size: 1.1rem;
        }}

        .collapse-icon {{
            transition: transform 0.3s;
            color: var(--text-secondary);
        }}

        .vs-badge {{
            padding: 0.4rem 0.8rem;
            border-radius: 16px;
            font-size: 0.85rem;
            font-weight: 600;
        }}

        .badge-critical {{
            background: #fee;
            color: #c00;
        }}

        .badge-warning {{
            background: #fff8e1;
            color: #f57c00;
        }}

        .badge-match {{
            background: #e8f5e9;
            color: #2e7d32;
        }}

        .vs-content {{
            padding: 0 1.5rem 1.5rem 1.5rem;
        }}

        .redundancy-warning {{
            background: #fff3e0;
            border-left: 4px solid #ff9800;
            padding: 1rem;
            margin-bottom: 1rem;
            border-radius: 4px;
        }}

        [data-theme="dark"] .redundancy-warning {{
            background: #3e2723;
        }}

        .comparison-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.95rem;
        }}

        .comparison-table thead {{
            background: var(--bg-secondary);
        }}

        .comparison-table th {{
            padding: 1rem;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid var(--border-color);
        }}

        .comparison-table td {{
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--border-color);
        }}

        .comparison-table tr:hover {{
            background: var(--bg-secondary);
        }}

        .config-key {{
            font-weight: 500;
            color: var(--text-secondary);
        }}

        .config-value {{
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
        }}

        .diff-highlight {{
            background: #fff3cd;
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-weight: 500;
        }}

        .ip-highlight {{
            background: #ffe0b2;
            padding: 0.2rem 0.4rem;
            border-radius: 4px;
            font-weight: 600;
            color: #e65100;
        }}

        .missing {{
            color: var(--accent-danger);
            font-style: italic;
        }}

        [data-theme="dark"] .diff-highlight {{
            background: #3e2723;
            color: #ffb74d;
        }}

        [data-theme="dark"] .ip-highlight {{
            background: #3e2723;
            color: #ff9800;
        }}

        .no-results {{
            display: none;
            text-align: center;
            padding: 3rem;
            color: var(--text-secondary);
            font-size: 1.2rem;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 F5 LTM Site-Aware Configuration Comparison</h1>
        <div class="header-meta">
            <div><strong>Site 1 (NJ):</strong> {server1}</div>
            <div><strong>Site 2 (HRZ):</strong> {server2}</div>
            <div><strong>Timestamp:</strong> {timestamp}</div>
        </div>
    </div>

    <div class="container">
        <div class="stats">
            <div class="stat-card total">
                <div class="stat-value">{stats['total']}</div>
                <div class="stat-label">Total Virtual Servers</div>
            </div>
            <div class="stat-card critical">
                <div class="stat-value">{stats['critical']}</div>
                <div class="stat-label">Critical ({stats['critical_pct']}%)</div>
            </div>
            <div class="stat-card warnings">
                <div class="stat-value">{stats['warnings']}</div>
                <div class="stat-label">Warnings ({stats['warning_pct']}%)</div>
            </div>
            <div class="stat-card matches">
                <div class="stat-value">{stats['matches']}</div>
                <div class="stat-label">Matches ({stats['match_pct']}%)</div>
            </div>
            <div class="stat-card no-redundancy">
                <div class="stat-value">{stats['no_redundancy']}</div>
                <div class="stat-label">No Redundancy</div>
            </div>
        </div>

        <div class="insights-panel" id="insightsPanel"></div>

        <div class="controls">
            <div class="search-box">
                <span class="search-icon">🔍</span>
                <input type="text" id="searchInput" placeholder="Search virtual servers..." oninput="filterServers()">
            </div>
            <div class="filter-buttons">
                <button class="filter-btn active" onclick="filterByType('all')">All</button>
                <button class="filter-btn" onclick="filterByType('differences')">Differences</button>
                <button class="filter-btn" onclick="filterByType('critical')">Critical</button>
                <button class="filter-btn" onclick="filterByType('warnings')">Warnings</button>
                <button class="filter-btn" onclick="filterByType('matches')">Matches</button>
            </div>
            <button class="theme-toggle" onclick="toggleTheme()">🌓 Toggle Theme</button>
            <button class="export-btn" onclick="exportDifferences()">📥 Export Differences</button>
        </div>

        <div id="comparisonContainer"></div>
        <div id="noResults" class="no-results">No virtual servers match your search.</div>
    </div>

    <script>
        const comparisonData = {comparison_json};
        const insights = {insights_json};
        const server1Name = '{server1}';
        const server2Name = '{server2}';
        let currentFilter = 'all';

        // Render insights panel
        function renderInsights() {{
            const panel = document.getElementById('insightsPanel');
            const riskClass = insights.risk_level === 'HIGH' ? 'risk-high' : (insights.risk_level === 'MEDIUM' ? 'risk-medium' : 'risk-low');
            
            let html = `
                <div class="insights-header">
                    <span class="insights-title">🎯 Smart Analysis Insights</span>
                    <span class="risk-badge ${{riskClass}}">
                        🔴 Critical: ${{insights.critical_count}}/${{insights.total_count}} (${{insights.critical_percentage}}%)
                    </span>
                    <span class="risk-badge ${{riskClass}}" style="margin-left: 0.5rem;">
                        Risk Level: ${{insights.risk_level}}
                    </span>
                    <span style="color: var(--text-secondary); margin-left: auto; font-size: 0.9rem;">${{insights.assessment}}</span>
                </div>
                <div class="insights-grid" id="insightsGrid"></div>
            `;
            
            panel.innerHTML = html;
            
            const grid = document.getElementById('insightsGrid');
            
            // Alerts
            if (insights.alerts && insights.alerts.length > 0) {{
                const alertSection = document.createElement('div');
                alertSection.className = 'insight-section alerts';
                alertSection.innerHTML = `
                    <div class="insight-title">🚨 Alerts</div>
                    ${{insights.alerts.map(alert => `
                        <div class="insight-message">${{alert.message}}</div>
                    `).join('')}}
                `;
                grid.appendChild(alertSection);
            }}
            
            // Warnings
            if (insights.warnings && insights.warnings.length > 0) {{
                const warningSection = document.createElement('div');
                warningSection.className = 'insight-section warnings';
                warningSection.innerHTML = `
                    <div class="insight-title">⚠️ Warnings</div>
                    ${{insights.warnings.map(warning => `
                        <div class="insight-message">${{warning.message}}</div>
                    `).join('')}}
                `;
                grid.appendChild(warningSection);
            }}
            
            // Info
            if (insights.info && insights.info.length > 0) {{
                const infoSection = document.createElement('div');
                infoSection.className = 'insight-section info';
                infoSection.innerHTML = `
                    <div class="insight-title">ℹ️ Information</div>
                    ${{insights.info.map(info => `
                        <div class="insight-message">${{info.message}}</div>
                    `).join('')}}
                `;
                grid.appendChild(infoSection);
            }}

            // Show empty state if no insights
            if ((!insights.alerts || insights.alerts.length === 0) && 
                (!insights.warnings || insights.warnings.length === 0) && 
                (!insights.info || insights.info.length === 0)) {{
                grid.innerHTML = '<div class="empty-insights">✅ No issues detected - all configurations look good!</div>';
            }}
        }}

        function renderComparisons() {{
            const container = document.getElementById('comparisonContainer');
            container.innerHTML = '';

            comparisonData.forEach((vs) => {{
                const vsElement = document.createElement('div');
                // DEFAULT COLLAPSED STATE
                vsElement.className = 'virtual-server collapsed';
                vsElement.dataset.name = vs.name.toLowerCase();
                vsElement.dataset.hasDiff = vs.hasDifferences;
                vsElement.dataset.isCritical = vs.isCritical;
                vsElement.dataset.isWarning = vs.isWarning;

                // Badge based on classification
                let badge = '';
                if (vs.badgeType === 'CRITICAL') {{
                    badge = '<span class="vs-badge badge-critical">🔴 Critical</span>';
                }} else if (vs.badgeType === 'WARNING' || vs.hasNoRedundancy) {{
                    badge = '<span class="vs-badge badge-warning">⚠️ Warning</span>';
                }} else {{
                    badge = '<span class="vs-badge badge-match">✅ Match</span>';
                }}

                let redundancyWarning = '';
                if (vs.hasNoRedundancy) {{
                    const missingSite = vs.missingInFile1 ? 'Site 1 (NJ)' : 'Site 2 (HRZ)';
                    redundancyWarning = `
                        <div class="redundancy-warning">
                            <strong>⚠️ No Redundancy:</strong> This virtual server only exists in ${{vs.missingInFile1 ? 'Site 2 (HRZ)' : 'Site 1 (NJ)'}}. Missing in ${{missingSite}}.
                        </div>
                    `;
                }}

                vsElement.innerHTML = `
                    <div class="vs-header ${{vs.hasDifferences ? 'has-diff' : 'no-diff'}}" onclick="toggleVS(this)">
                        <div class="vs-title">
                            <span class="collapse-icon">▼</span>
                            <span>${{vs.name}}</span>
                            ${{badge}}
                            <span style="font-size: 0.8rem; color: var(--text-secondary); font-weight: normal;">[${{vs.environment}}]</span>
                        </div>
                        <span style="color: var(--text-secondary); font-size: 0.9rem;">${{vs.configurations.length}} items</span>
                    </div>
                    <div class="vs-content">
                        ${{redundancyWarning}}
                        <table class="comparison-table">
                            <thead>
                                <tr>
                                    <th style="width: 200px;">Configuration Item</th>
                                    <th>${{server1Name}} (NJ)</th>
                                    <th>${{server2Name}} (HRZ)</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${{vs.configurations.map(config => `
                                    <tr>
                                        <td class="config-key">${{config.key}}</td>
                                        <td class="config-value">
                                            ${{config.file1 === '(missing)' ? '<span class="missing">(missing)</span>' :
                                                (config.isDiff 
                                                    ? (config.isIP 
                                                        ? `<span class="ip-highlight">${{config.file1}}</span>` 
                                                        : `<span class="diff-highlight">${{config.file1}}</span>`)
                                                    : config.file1)}}
                                        </td>
                                        <td class="config-value">
                                            ${{config.file2 === '(missing)' ? '<span class="missing">(missing)</span>' :
                                                (config.isDiff 
                                                    ? (config.isIP 
                                                        ? `<span class="ip-highlight">${{config.file2}}</span>` 
                                                        : `<span class="diff-highlight">${{config.file2}}</span>`)
                                                    : config.file2)}}
                                        </td>
                                    </tr>
                                `).join('')}}
                            </tbody>
                        </table>
                    </div>
                `;

                container.appendChild(vsElement);
            }});
        }}

        function toggleVS(header) {{
            const vs = header.parentElement;
            vs.classList.toggle('collapsed');
        }}

        function filterServers() {{
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            const servers = document.querySelectorAll('.virtual-server');
            let visibleCount = 0;

            servers.forEach(server => {{
                const name = server.dataset.name;
                const matchesSearch = name.includes(searchTerm);
                const matchesFilter = checkFilterMatch(server);

                if (matchesSearch && matchesFilter) {{
                    server.classList.remove('hidden');
                    visibleCount++;
                }} else {{
                    server.classList.add('hidden');
                }}
            }});

            document.getElementById('noResults').style.display = visibleCount === 0 ? 'block' : 'none';
        }}

        function filterByType(type) {{
            currentFilter = type;
            document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            filterServers();
        }}

        function checkFilterMatch(server) {{
            const hasDiff = server.dataset.hasDiff === 'true';
            const isCritical = server.dataset.isCritical === 'true';
            const isWarning = server.dataset.isWarning === 'true';

            switch(currentFilter) {{
                case 'all': return true;
                case 'differences': return hasDiff;
                case 'matches': return !hasDiff;
                case 'critical': return isCritical;
                case 'warnings': return isWarning;
                default: return true;
            }}
        }}

        function toggleTheme() {{
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
        }}

        function exportDifferences() {{
            const differencesOnly = comparisonData.filter(vs => vs.hasDifferences);
            const report = {{
                timestamp: '{timestamp}',
                servers: {{
                    site1_nj: server1Name,
                    site2_hrz: server2Name
                }},
                summary: {{
                    total: comparisonData.length,
                    differences: differencesOnly.length,
                    critical: comparisonData.filter(vs => vs.isCritical).length,
                    warnings: comparisonData.filter(vs => vs.isWarning).length,
                    no_redundancy: comparisonData.filter(vs => vs.hasNoRedundancy).length
                }},
                insights: insights,
                differences: differencesOnly
            }};

            const blob = new Blob([JSON.stringify(report, null, 2)], {{ type: 'application/json' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `f5-site-comparison-${{Date.now()}}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }}

        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        
        renderInsights();
        renderComparisons();
    </script>
</body>
</html>
"""
    
    return html_template


def create_zip(html_file: str, zip_path: str) -> str:
    """Create compressed zip file of the HTML report"""
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        zipf.write(html_file, arcname=Path(html_file).name)
    logger.info("Compressed report created")
    return zip_path


def upload_to_s3(file_path: str, bucket: str, key: str) -> str:
    """Upload file to S3 and return presigned URL"""
    try:
        s3_client.upload_file(file_path, bucket, key)
        logger.info(f"Uploaded {key} to S3 bucket {bucket}")
        
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=604800
        )
        return url
    except ClientError as e:
        logger.error(f"Error uploading to S3: {e}")
        raise


def send_enhanced_webhook(
    webhook_url: str,
    server1: str,
    server2: str,
    stats: Dict[str, Any],
    insights: Dict[str, Any],
    s3_url: str,
    timestamp: str
) -> None:
    """Send enhanced Teams/Slack webhook with insights"""
    import urllib.request
    import urllib.parse
    
    try:
        # Determine color based on risk level
        if insights['risk_level'] == 'HIGH':
            color = "FF0000"  # Red
            title = "🚨 F5 Configuration - HIGH RISK Changes Detected"
        elif insights['risk_level'] == 'MEDIUM':
            color = "FFA500"  # Orange
            title = "⚠️ F5 Configuration - Changes Require Review"
        elif stats.get('differences', 0) > 0:
            color = "FFD700"  # Yellow
            title = "📋 F5 Configuration - Changes Detected"
        else:
            color = "00FF00"  # Green
            title = "✅ F5 Configuration - No Changes"
        
        # Build facts list with insights
        facts = [
            {"name": "Comparison", "value": f"{server1} (NJ) vs {server2} (HRZ)"},
            {"name": "Timestamp", "value": timestamp},
            {"name": "Total Virtual Servers", "value": str(stats.get('total', 0))},
            {"name": "Critical Count", "value": f"{insights['critical_count']} ({insights['critical_percentage']}%)"},
            {"name": "Warning Count", "value": f"{insights['warning_count']} ({insights['warning_percentage']}%)"},
            {"name": "Match Count", "value": f"{insights['match_count']} ({insights['match_percentage']}%)"},
            {"name": "No Redundancy", "value": str(stats.get('no_redundancy', 0))},
            {"name": "Risk Level", "value": insights['risk_level']},
            {"name": "Assessment", "value": insights['assessment']}
        ]
        
        # Add alerts
        if insights['alerts']:
            alert_text = "\n".join([f"• {a['message']}" for a in insights['alerts'][:3]])
            facts.append({"name": "🚨 Alerts", "value": alert_text})
        
        # Add warnings
        if insights['warnings']:
            warning_text = "\n".join([f"• {w['message']}" for w in insights['warnings'][:3]])
            facts.append({"name": "⚠️ Warnings", "value": warning_text})
        
        card = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": color,
            "summary": title,
            "sections": [
                {
                    "activityTitle": title,
                    "facts": facts,
                    "markdown": True
                }
            ],
            "potentialAction": [
                {
                    "@type": "OpenUri",
                    "name": "📊 View Detailed Report",
                    "targets": [{"os": "default", "uri": s3_url}]
                }
            ]
        }
        
        data = json.dumps(card).encode('utf-8')
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={'Content-Type': 'application/json'},
            timeout=10  # Add timeout
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            result = response.read()
            logger.info(f"Webhook sent successfully: {result.decode('utf-8')}")
            
    except Exception as e:
        logger.error(f"Error sending webhook: {e}")
        # Don't fail the whole function


def lambda_handler(event, context):
    """AWS Lambda handler function"""
    logger.info("Starting F5 LTM virtual server comparison with smart analysis")
    logger.info(f"Event: {json.dumps(event)}")
    
    server1 = event.get('server1', os.environ.get('SERVER1', '10.x.x.x'))
    server2 = event.get('server2', os.environ.get('SERVER2', '10.x.x.x'))
    config_path = event.get('config_path', os.environ.get('CONFIG_PATH', '/home/vboxuser/bigip.conf'))
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Get SSH credentials
            credentials = get_ssh_credentials()
            username = credentials['username']
            private_key = credentials['private_key']
            
            ssh_key_path = os.path.join(temp_dir, 'id_rsa')
            with open(ssh_key_path, 'w') as f:
                f.write(private_key)
            os.chmod(ssh_key_path, 0o600)
            logger.info(f"SSH key written to {ssh_key_path}")
            
            # Copy configurations from both servers
            file1_path = os.path.join(temp_dir, 'config1.conf')
            file2_path = os.path.join(temp_dir, 'config2.conf')
            
            copy_file_from_remote(server1, username, ssh_key_path, config_path, file1_path)
            copy_file_from_remote(server2, username, ssh_key_path, config_path, file2_path)
            
            # Read and mask configurations
            with open(file1_path, 'r') as f:
                content1 = mask_sensitive_data(f.read())
            
            with open(file2_path, 'r') as f:
                content2 = mask_sensitive_data(f.read())
            
            # Parse virtual servers
            logger.info("Parsing LTM virtual server configurations")
            vs1 = parse_ltm_virtual_servers(content1)
            vs2 = parse_ltm_virtual_servers(content2)
            
            logger.info(f"Found {len(vs1)} virtual servers in {server1}")
            logger.info(f"Found {len(vs2)} virtual servers in {server2}")
            
            # Compare configurations with site-aware logic
            comparison_data = compare_virtual_servers(vs1, vs2)
            
            # Smart analysis with environment-aware risk scoring
            logger.info("Running smart pattern analysis")
            insights = analyze_patterns(comparison_data)
            logger.info(f"Analysis complete - Risk Level: {insights['risk_level']}")
            logger.info(f"Critical: {insights['critical_count']}/{insights['total_count']} ({insights['critical_percentage']}%)")
            logger.info(f"Assessment: {insights['assessment']}")
            
            # Statistics
            stats = {
                'total': len(comparison_data),
                'differences': sum(1 for vs in comparison_data if vs['hasDifferences']),
                'critical': sum(1 for vs in comparison_data if vs['isCritical']),
                'warnings': sum(1 for vs in comparison_data if vs['isWarning']),
                'no_redundancy': sum(1 for vs in comparison_data if vs['hasNoRedundancy'])
            }
            
            # Generate report
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')
            html_content = generate_enhanced_html(comparison_data, server1, server2, timestamp, insights)
            
            html_file = os.path.join(temp_dir, 'comparison.html')
            zip_file = os.path.join(temp_dir, 'comparison.zip')
            
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.info("Enhanced HTML report generated")
            
            # Upload to S3
            create_zip(html_file, zip_file)
            s3_timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            s3_key = f"comparisons/{s3_timestamp}_f5_ltm_comparison.zip"
            s3_url = upload_to_s3(zip_file, BUCKET_NAME, s3_key)
            
            # Store metadata in DynamoDB
            store_comparison_metadata(
                server1, server2, comparison_data, insights, s3_url,
                datetime.now().isoformat()
            )
            
            # Publish CloudWatch metrics
            publish_cloudwatch_metrics(comparison_data, insights)
            
            # Send webhook with insights
            if TEAMS_WEBHOOK_URL:
                send_enhanced_webhook(
                    TEAMS_WEBHOOK_URL, server1, server2, stats, insights, s3_url, timestamp
                )
            
            logger.info("F5 LTM comparison completed successfully")
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'F5 LTM comparison completed successfully',
                    'servers': [server1, server2],
                    's3_url': s3_url,
                    'timestamp': s3_timestamp,
                    'statistics': stats,
                    'insights': insights
                })
            }
            
        except Exception as e:
            logger.error(f"Error in lambda handler: {e}", exc_info=True)
            
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'message': 'Error during F5 LTM comparison',
                    'error': str(e)
                })
            }