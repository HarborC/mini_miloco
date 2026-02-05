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

SHOW_LOGS=""
for arg in "$@"; do
  case "$arg" in
    --logs)
      SHOW_LOGS=1
      ;;
  esac
done

mkdir -p "$STATE_DIR"

if [[ "$OS_NAME" == "Darwin" ]]; then
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

  exec python -m mini_miloco.http \
    --token-file "$TOKEN_FILE" \
    --cache-dir "$CACHE_DIR" \
    --camera-snapshot-dir "$CAMERA_DIR" \
    --cloud-server "$CLOUD_SERVER" \
    --redirect-uri "$REDIRECT_URI" \
    ${DEVICE_UUID:+--uuid "$DEVICE_UUID"} \
    --host "$HOST" \
    --port "$PORT" \
    --path "$PATH_PREFIX"
fi

if [[ "$OS_NAME" == "Linux" ]]; then
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required on Linux. Please install Docker first."
    exit 1
  fi

  cd "$ROOT_DIR"
  docker compose up -d --build
  if [[ -n "$SHOW_LOGS" ]]; then
    exec docker compose logs -f
  fi
  echo "Mini Miloco is running via Docker."
  echo "URL: http://$HOST:$PORT$PATH_PREFIX"
  exit 0
fi

echo "Unsupported OS: $OS_NAME"
exit 1
