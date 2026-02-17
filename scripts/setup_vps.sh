#!/bin/bash

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
sudo apt update
sudo apt install -y docker-ce

# Install Docker Compose (plugin)
sudo apt install -y docker-compose-plugin

# Allow current user to run docker without sudo
sudo usermod -aG docker ${USER}
echo "Docker installed. Please log out and back in for changes to take effect."

# Install Git
sudo apt install -y git

# Install UFW (Firewall)
sudo apt install -y ufw

# Configure UFW
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# Deny incoming by default, allow outgoing
sudo ufw default deny incoming
sudo ufw default allow outgoing
# Enable UFW
echo "y" | sudo ufw enable

# Create project directory
mkdir -p ~/cubari-hakken
# Set permissions (optional, just ensuring ownership)
chown -R ${USER}:${USER} ~/cubari-hakken

echo "Setup complete. Remember to configure Oracle Cloud Security List (VCN)!"
