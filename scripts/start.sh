#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

OS_NAME="$(uname -s)"

STATE_DIR="${MINI_MILOCO_STATE_DIR:-$ROOT_DIR/.cache}"
TOKEN_FILE="${MINI_MILOCO_TOKEN_FILE:-$STATE_DIR/miot_oauth.json}"
CACHE_DIR="${MINI_MILOCO_CACHE_DIR:-$STATE_DIR/miot_cache}"
CAMERA_DIR="${MINI_MILOCO_CAMERA_DIR:-$STATE_DIR/miot_camera_snapshots}"
HOST="${MINI_MILOCO_HOST:-127.0.0.1}"
PORT="${MINI_MILOCO_PORT:-2324}"
PATH_PREFIX="${MINI_MILOCO_PATH:-/mcp}"
CLOUD_SERVER="${MINI_MILOCO_CLOUD_SERVER:-cn}"
REDIRECT_URI="${MINI_MILOCO_REDIRECT_URI:-https://mico.api.mijia.tech/login_redirect}"
DEVICE_UUID="${MINI_MILOCO_UUID:-}"
TMUX_SESSION="${MINI_MILOCO_TMUX_SESSION:-mini-miloco}"

mkdir -p "$STATE_DIR"

if [[ "$OS_NAME" == "Darwin" ]]; then
  if ! command -v tmux >/dev/null 2>&1; then
    echo "tmux is required on macOS. Please install tmux first."
    exit 1
  fi

  VENV_DIR="$ROOT_DIR/.venv"

  if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
  fi
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
  python -m pip install --upgrade pip setuptools wheel
  if python -m pip install -e "$ROOT_DIR"; then
    :
  else
    echo "Editable install failed; falling back to non-editable install."
    python -m pip install "$ROOT_DIR"
  fi

  START_CMD=$(cat <<CMD
set -euo pipefail
cd "$ROOT_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
exec python -m mini_miloco.http \\
  --token-file "$TOKEN_FILE" \\
  --cache-dir "$CACHE_DIR" \\
  --camera-snapshot-dir "$CAMERA_DIR" \\
  --cloud-server "$CLOUD_SERVER" \\
  --redirect-uri "$REDIRECT_URI" \\
  ${DEVICE_UUID:+--uuid "$DEVICE_UUID"} \\
  --host "$HOST" \\
  --port "$PORT" \\
  --path "$PATH_PREFIX"
CMD
)

  if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
    read -r -p "tmux session '$TMUX_SESSION' exists. Restart it? [y/N] " RESTART_TMUX
    if [[ "$RESTART_TMUX" =~ ^[Yy]$ ]]; then
      tmux kill-session -t "$TMUX_SESSION"
    else
      echo "Aborted."
      exit 0
    fi
  fi

  tmux new-session -d -s "$TMUX_SESSION" "bash -lc '$START_CMD'"
  echo "Started Mini Miloco in tmux session: $TMUX_SESSION"
  echo "Attach: tmux attach -t $TMUX_SESSION"
  exit 0
fi

if [[ "$OS_NAME" == "Linux" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required on Linux. Please install Docker first."
    exit 1
  fi

  cd "$ROOT_DIR"
  docker compose up -d --build
  echo "Mini Miloco is running via Docker."
  echo "URL: http://$HOST:$PORT$PATH_PREFIX"
  exit 0
fi

echo "Unsupported OS: $OS_NAME"
exit 1
