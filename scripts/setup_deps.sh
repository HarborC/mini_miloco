#!/usr/bin/env bash
set -euo pipefail

OS_NAME="$(uname -s)"

if [[ "$OS_NAME" == "Darwin" ]]; then
  if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew is required. Please install Homebrew first."
    echo "See: https://brew.sh"
    exit 1
  fi
  brew update
  brew install tmux python@3.11 ffmpeg
  echo "Done. Ensure python3 points to 3.11 or set MINI_MILOCO_PY if needed."
  exit 0
fi

if [[ "$OS_NAME" == "Linux" ]]; then
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
$(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    echo "Docker installed. You may want to run: sudo usermod -aG docker $USER"
    exit 0
  fi

  echo "Unsupported Linux distro: only apt-based is handled. Please install Docker manually."
  exit 1
fi

echo "Unsupported OS: $OS_NAME"
exit 1
