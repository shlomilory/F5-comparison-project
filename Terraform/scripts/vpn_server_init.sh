#!/bin/bash
# OpenVPN Server Initialization Script
# This script is run automatically when the EC2 instance launches

set -e

# Update system
apt-get update
apt-get upgrade -y

# Install OpenVPN and Easy-RSA
apt-get install -y openvpn easy-rsa iptables-persistent

# Enable IP forwarding
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -p

# Setup Easy-RSA
make-cadir ~/openvpn-ca
cd ~/openvpn-ca

# Configure Easy-RSA
cat > vars << 'EOF'
set_var EASYRSA_REQ_COUNTRY    "US"
set_var EASYRSA_REQ_PROVINCE   "California"
set_var EASYRSA_REQ_CITY       "San Francisco"
set_var EASYRSA_REQ_ORG        "F5Lab"
set_var EASYRSA_REQ_EMAIL      "admin@f5lab.local"
set_var EASYRSA_REQ_OU         "IT"
set_var EASYRSA_ALGO           "ec"
set_var EASYRSA_DIGEST         "sha512"
EOF

# Initialize PKI
./easyrsa init-pki

# Build CA (non-interactive)
echo "yes" | ./easyrsa build-ca nopass

# Generate server certificate
echo "yes" | ./easyrsa build-server-full server nopass

# Generate Diffie-Hellman parameters
./easyrsa gen-dh

# Generate TLS auth key
openvpn --genkey secret pki/ta.key

# Copy certificates to OpenVPN directory
cp pki/ca.crt /etc/openvpn/
cp pki/issued/server.crt /etc/openvpn/
cp pki/private/server.key /etc/openvpn/
cp pki/dh.pem /etc/openvpn/
cp pki/ta.key /etc/openvpn/

# Create OpenVPN server configuration
cat > /etc/openvpn/server.conf << 'EOF'
# OpenVPN Server Configuration
port 1194
proto udp
dev tun

# Certificates and keys
ca ca.crt
cert server.crt
key server.key
dh dh.pem
tls-auth ta.key 0

# Network settings
server 10.8.0.0 255.255.255.0
topology subnet

# Routes to push to clients
push "route ${vpc_cidr}"

# Route from clients to home network
route ${home_network_cidr}

# Client settings
client-to-client
keepalive 10 120
cipher AES-256-GCM
auth SHA256
persist-key
persist-tun

# Logging
status /var/log/openvpn/status.log
log-append /var/log/openvpn/openvpn.log
verb 3

# Security
user nobody
group nogroup
EOF

# Create log directory
mkdir -p /var/log/openvpn

# Enable NAT for traffic between VPC and home network
iptables -t nat -A POSTROUTING -s ${vpc_cidr} -o tun0 -j MASQUERADE
iptables -A FORWARD -i tun0 -j ACCEPT
iptables -A FORWARD -o tun0 -j ACCEPT

# Save iptables rules
netfilter-persistent save

# Enable and start OpenVPN
systemctl enable openvpn@server
systemctl start openvpn@server

# Generate client certificate
cd ~/openvpn-ca
echo "yes" | ./easyrsa build-client-full client1 nopass

echo "VPN server setup complete!"
