# VPN Server EC2 Instance

# SSH Key Pair for VPN Server
resource "aws_key_pair" "vpn_server" {
  count = var.enable_vpn ? 1 : 0
  
  key_name   = "f5-vpn-server-key"
  public_key = file("~/.ssh/f5_vpn_server.pub")

  tags = merge(local.common_tags, {
    Name = "f5-vpn-server-key"
  })
}

# VPN Server EC2 Instance
resource "aws_instance" "vpn_server" {
  count = var.enable_vpn ? 1 : 0
  
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.vpn_instance_type
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.vpn_server[0].id]
  key_name               = aws_key_pair.vpn_server[0].key_name
  
  # Disable source/destination check (required for routing)
  source_dest_check = false

  # User data script to install and configure OpenVPN
  user_data = templatefile("${path.module}/scripts/vpn_server_init.sh", {
    home_network_cidr = var.home_network_cidr
    vpc_cidr          = var.vpc_cidr
  })

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  tags = merge(local.common_tags, {
    Name = "f5-vpn-server"
  })
}

# Elastic IP for VPN Server
resource "aws_eip" "vpn_server" {
  count = var.enable_vpn ? 1 : 0
  
  instance = aws_instance.vpn_server[0].id
  domain   = "vpc"

  tags = merge(local.common_tags, {
    Name = "f5-vpn-server-eip"
  })

  depends_on = [aws_internet_gateway.main]
}
