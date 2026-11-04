#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 server (e.g. AWS Lightsail, Mumbai) for one Mitra
# environment. Run as the default user with sudo:  bash server-setup.sh
# Installs Docker, a 2 GB swap file, a deploy user for GitHub Actions, /opt/mitra and the
# nightly database backup. The cloud firewall (Lightsail "Networking" tab) must allow only:
#   TCP 22 (your IP only), TCP 80, TCP 443, UDP 443, UDP 10000-65535 (WebRTC media).
set -euo pipefail

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo systemctl enable --now docker

# Swap: builds never run here, but a spike should slow the server down, not kill Postgres.
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

# The deploy user: GitHub Actions logs in with its own SSH key and may only run Docker.
if ! id deploy >/dev/null 2>&1; then
  sudo useradd --create-home --shell /bin/bash deploy
fi
sudo usermod -aG docker deploy
sudo install -d -o deploy -g deploy -m 700 /home/deploy/.ssh
sudo touch /home/deploy/.ssh/authorized_keys
sudo chown deploy:deploy /home/deploy/.ssh/authorized_keys
sudo chmod 600 /home/deploy/.ssh/authorized_keys

# App directory: compose.yml, Caddyfile and postgres-init.sql are copied in by each deploy;
# .env and env/*.env are written once by hand (secrets never leave the server).
sudo install -d -o deploy -g deploy -m 750 /opt/mitra /opt/mitra/env /opt/mitra/backups

# Nightly database backup at 02:30 IST, 14 days kept (deploy/backup.sh).
sudo tee /etc/cron.d/mitra-backup >/dev/null <<'CRON'
CRON_TZ=Asia/Kolkata
30 2 * * * deploy /opt/mitra/backup.sh >> /opt/mitra/backups/backup.log 2>&1
CRON

# Security updates install themselves.
sudo apt-get install -y unattended-upgrades >/dev/null
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo "Done. Next: add the GitHub deploy key to /home/deploy/.ssh/authorized_keys and write"
echo "/opt/mitra/.env, /opt/mitra/env/core.env, /opt/mitra/env/voice.env (deploy/README.md)."
