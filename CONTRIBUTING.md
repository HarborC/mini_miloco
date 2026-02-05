# Contributing

Thanks for your interest in Mini Miloco.

## Development Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
mkdir -p .cache
```

## Local Run
```bash
mini-miloco-auth --cloud-server cn --token-file .cache/miot_oauth.json
mini-miloco-http \
  --token-file .cache/miot_oauth.json \
  --cache-dir .cache/miot_cache \
  --camera-snapshot-dir .cache/miot_camera_snapshots \
  --host 127.0.0.1 --port 2324
```

## Linux (Docker)
```bash
bash scripts/setup_deps.sh
docker compose up -d --build
```

## Notes
- Please avoid adding breaking changes to the MCP tool names.
- If you add new tools, update `README.md` examples accordingly.
