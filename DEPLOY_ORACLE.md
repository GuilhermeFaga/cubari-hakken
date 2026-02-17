# Deploying Cubari-Hakken to Oracle Cloud VPS

This guide will walk you through deploying your Cubari-Hakken instance to an **Oracle Cloud Always Free VPS**.

## Prerequisites

1.  **Oracle Cloud Account**: Sign up for an Oracle Cloud account (Always Free tier is sufficient).
2.  **GitHub Repository**: Ensure this project is pushed to your GitHub repository.
3.  **SSH Key**: You'll need the SSH key (private) you used to create the VPS instance.

## Step 1: Create Oracle VPS Instance

1.  Log in to the **Oracle Cloud Console**.
2.  Navigate to **Compute > Instances** and click **Create Instance**.
3.  **Image & Shape**:
    *   **Image**: Canonical Ubuntu 22.04 or 24.04 (ARM-compatible).
    *   **Shape**: **VM.Standard.A1.Flex** (Ampere ARM). This is the powerful free tier option (up to 4 OCPUs, 24GB RAM).
4.  **Networking**: Create a new Virtual Cloud Network (VCN) or use existing.
5.  **SSH Keys**: **IMPORTANT:** Save the private key (`.key` file) provided by Oracle or upload your own public key. You will need this to connect.
6.  Click **Create**.

## Step 2: Configure Firewall (Security List)

By default, Oracle blocks incoming traffic. You must explicitly allow HTTP (80) and HTTPS (443).

1.  Go to **Networking > Virtual Cloud Networks**.
2.  Click on your VCN name.
3.  Click **Security Lists** (left menu) > **Default Security List for...**.
4.  Click **Add Ingress Rules**.
5.  Add a rule for **HTTP**:
    *   **Source CIDR**: `0.0.0.0/0`
    *   **IP Protocol**: TCP
    *   **Destination Port Range**: `80`
6.  Add a rule for **HTTPS**:
    *   **Source CIDR**: `0.0.0.0/0`
    *   **IP Protocol**: TCP
    *   **Destination Port Range**: `443`
7.  Click **Add Ingress Rules**.

## Step 3: Server Setup

1.  **SSH into your VPS**:
    ```bash
    ssh -i /path/to/your/private.key ubuntu@<YOUR_VPS_IP>
    ```

2.  **Clone the Repository**:
    Update your package list and install git if needed:
    ```bash
    sudo apt update && sudo apt install -y git
    ```

    Since this is likely a private repository, you need to set up authentication.
    
    *Option A: HTTPS with Token (Easiest)*
    ```bash
    git clone https://<YOUR_GITHUB_TOKEN>@github.com/<YOUR_USERNAME>/cubari-hakken.git
    cd cubari-hakken
    ```

    *Option B: SSH (Recommended)*
    Generate a key pair on the server:
    ```bash
    ssh-keygen -t ed25519 -C "deploy@oracle"
    cat ~/.ssh/id_ed25519.pub
    ```
    Add this public key to your GitHub Repo > Settings > Deploy Keys.
    Then clone:
    ```bash
    git clone git@github.com:<YOUR_USERNAME>/cubari-hakken.git
    cd cubari-hakken
    ```

3.  **Run the Setup Script**:
    Now that the code is on the server, run the setup script included in the repo.
    ```bash
    chmod +x scripts/setup_vps.sh
    ./scripts/setup_vps.sh
    ```
    This script installs Docker, Docker Compose, UFW, and configures the firewall.

## Step 4: GitHub Secrets Configuration

Go to your GitHub Repository -> **Settings > Secrets and variables > Actions** and add the following secrets:

| Secret Name | Value |
| :--- | :--- |
| `VPS_HOST` | The Public IP address of your Oracle VPS. |
| `VPS_USER` | Usually `ubuntu`. |
| `VPS_SSH_KEY` | The contents of your **private SSH key** (the one used to log in to the VPS). |
| `APP_GITHUB_TOKEN` | A GitHub Personal Access Token (classic) with `repo` scope for the application to use for API calls. |

## Step 5: Initial Deployment

1.  **Push to Main**: The GitHub Action workflow is triggered on every push to the `main` branch.
2.  Commit and push your changes.
3.  Go to the **Actions** tab in your GitHub repository to monitor the deployment.

## Troubleshooting

*   **SSH Connection Failed**: Verify your `VPS_SSH_KEY` secret is correct and corresponds to the public key on the server (`~/.ssh/authorized_keys`).
*   **Permission Denied (publickey)**: Ensure the correct user (`ubuntu`) is used.
*   **Docker Permission Denied**: If the setup script didn't add the user to the `docker` group correctly, run `sudo usermod -aG docker $USER` and log out/in.

## DNS Configuration (Optional)

To use a custom domain:
1.  Point your domain's **A Record** to your VPS IP address.
2.  Update `Caddyfile` in the repository:
    ```caddyfile
    your-domain.com {
        reverse_proxy web:8000
        encode gzip
    }
    ```
    Replace `:80` with your domain name. Caddy will automatically provision SSL certificates.
