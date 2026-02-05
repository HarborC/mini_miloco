#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${MINI_MILOCO_REPO_URL:-https://github.com/HarborC/mini_miloco.git}"
BRANCH="${MINI_MILOCO_BRANCH:-main}"
INSTALL_DIR="${MINI_MILOCO_DIR:-$HOME/.mini-miloco/src/mini_miloco}"

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
    *)
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  echo "git is required but not found in PATH."
  exit 1
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
  echo "Updating existing repo: $INSTALL_DIR"
  git -C "$INSTALL_DIR" fetch --prune
  git -C "$INSTALL_DIR" checkout "$BRANCH"
  git -C "$INSTALL_DIR" pull --ff-only
else
  echo "Cloning repo to: $INSTALL_DIR"
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

echo "Running start.sh..."
ARGS=()
if [[ -n "$INSTALL_AUTOSTART" ]]; then
  ARGS+=("--autostart")
fi
if [[ -n "$UNINSTALL_AUTOSTART" ]]; then
  ARGS+=("--autostart-uninstall")
fi
if [[ -n "$ADD_CLAUDE" ]]; then
  ARGS+=("--add-claude")
fi

exec "$INSTALL_DIR/scripts/start.sh" "${ARGS[@]}"
