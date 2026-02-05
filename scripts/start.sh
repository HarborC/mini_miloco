#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

STATE_DIR="${MINI_MILOCO_STATE_DIR:-$HOME/.mini-miloco}"
VENV_DIR="${MINI_MILOCO_VENV_DIR:-$STATE_DIR/.venv}"
TOKEN_FILE="${MINI_MILOCO_TOKEN_FILE:-$STATE_DIR/miot_oauth.json}"
HOST="${MINI_MILOCO_HOST:-127.0.0.1}"
PORT="${MINI_MILOCO_PORT:-9000}"
PATH_PREFIX="${MINI_MILOCO_PATH:-/mcp}"
CLOUD_SERVER="${MINI_MILOCO_CLOUD_SERVER:-cn}"
REDIRECT_URI="${MINI_MILOCO_REDIRECT_URI:-https://mico.api.mijia.tech/login_redirect}"
DEVICE_UUID="${MINI_MILOCO_UUID:-}"

INSTALL_AUTOSTART="${MINI_MILOCO_AUTOSTART:-}"
UNINSTALL_AUTOSTART="${MINI_MILOCO_AUTOSTART_UNINSTALL:-}"
ADD_CLAUDE="${MINI_MILOCO_ADD_CLAUDE:-}"

for arg in "$@"; do
  case "$arg" in
    --autostart)
      INSTALL_AUTOSTART=1
      ;;
    --autostart-uninstall)
      UNINSTALL_AUTOSTART=1
      ;;
    --add-claude)
      ADD_CLAUDE=1
      ;;
  esac
done

if [[ -n "${MINI_MILOCO_PY:-}" ]]; then
  PYTHON="$MINI_MILOCO_PY"
elif [[ -x "$VENV_DIR/bin/python" ]]; then
  PYTHON="$VENV_DIR/bin/python"
else
  PYTHON="python3"
  mkdir -p "$STATE_DIR"
  "$PYTHON" -m venv "$VENV_DIR"
  PYTHON="$VENV_DIR/bin/python"
fi

echo "Using Python: $PYTHON"

"$PYTHON" -m pip install --upgrade pip setuptools wheel
if "$PYTHON" -m pip install -e "$ROOT_DIR"; then
  :
else
  echo "Editable install failed; falling back to non-editable install."
  "$PYTHON" -m pip install "$ROOT_DIR"
fi

echo "Starting Mini Miloco HTTP server..."
echo "URL: http://$HOST:$PORT$PATH_PREFIX"
if [[ -n "$ADD_CLAUDE" ]]; then
  if command -v claude >/dev/null 2>&1; then
    claude mcp add xiaomi-miot --transport http "http://$HOST:$PORT$PATH_PREFIX" || true
    echo "Claude MCP server added (or already exists)."
  else
    echo "Claude CLI not found in PATH. Skipping add."
  fi
else
  echo "If Claude CLI is available, you can add MCP server with:"
  echo "  claude mcp add xiaomi-miot --transport http http://$HOST:$PORT$PATH_PREFIX"
fi

if [[ -n "$UNINSTALL_AUTOSTART" ]]; then
  OS_NAME="$(uname -s)"
  if [[ "$OS_NAME" == "Darwin" ]]; then
    PLIST_PATH="$HOME/Library/LaunchAgents/mini-miloco-http.plist"
    launchctl stop com.harborc.mini-miloco-http 2>/dev/null || true
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    rm -f "$PLIST_PATH"
    echo "Removed launchd autostart: $PLIST_PATH"
  elif [[ "$OS_NAME" == "Linux" ]]; then
    SERVICE_PATH="$HOME/.config/systemd/user/mini-miloco-http.service"
    systemctl --user stop mini-miloco-http 2>/dev/null || true
    systemctl --user disable mini-miloco-http 2>/dev/null || true
    rm -f "$SERVICE_PATH"
    systemctl --user daemon-reload
    echo "Removed systemd autostart: $SERVICE_PATH"
  else
    echo "Autostart not supported on OS: $OS_NAME"
  fi
fi

if [[ -n "$INSTALL_AUTOSTART" ]]; then
  OS_NAME="$(uname -s)"
  if [[ "$OS_NAME" == "Darwin" ]]; then
    PLIST_PATH="$HOME/Library/LaunchAgents/mini-miloco-http.plist"
    cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.harborc.mini-miloco-http</string>
    <key>ProgramArguments</key>
    <array>
      <string>$PYTHON</string>
      <string>-m</string>
      <string>mini_miloco.http</string>
      <string>--token-file</string>
      <string>$TOKEN_FILE</string>
      <string>--cloud-server</string>
      <string>$CLOUD_SERVER</string>
      <string>--redirect-uri</string>
      <string>$REDIRECT_URI</string>
      <string>--host</string>
      <string>$HOST</string>
      <string>--port</string>
      <string>$PORT</string>
      <string>--path</string>
      <string>$PATH_PREFIX</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$STATE_DIR/mini-miloco-http.log</string>
    <key>StandardErrorPath</key>
    <string>$STATE_DIR/mini-miloco-http.err</string>
  </dict>
</plist>
EOF
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    launchctl load "$PLIST_PATH"
    launchctl start com.harborc.mini-miloco-http
    echo "Installed launchd autostart: $PLIST_PATH"
  elif [[ "$OS_NAME" == "Linux" ]]; then
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_DIR"
    SERVICE_PATH="$SYSTEMD_DIR/mini-miloco-http.service"
    cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Mini Miloco MCP HTTP Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$PYTHON -m mini_miloco.http --token-file $TOKEN_FILE --cloud-server $CLOUD_SERVER --redirect-uri $REDIRECT_URI --host $HOST --port $PORT --path $PATH_PREFIX
Restart=always
RestartSec=3
WorkingDirectory=$ROOT_DIR
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now mini-miloco-http
    echo "Installed systemd autostart: $SERVICE_PATH"
  else
    echo "Autostart not supported on OS: $OS_NAME"
  fi
fi

exec "$PYTHON" -m mini_miloco.http \
  --token-file "$TOKEN_FILE" \
  --cloud-server "$CLOUD_SERVER" \
  --redirect-uri "$REDIRECT_URI" \
  ${DEVICE_UUID:+--uuid "$DEVICE_UUID"} \
  ${MINI_MILOCO_DISABLE_LAN:+--disable-lan} \
  --host "$HOST" \
  --port "$PORT" \
  --path "$PATH_PREFIX"
