# Contributing

Thanks for your interest in Mini Miloco.

## Development Setup
```bash
pip install -e .
mkdir -p .cache
```

## Local Run
```bash
mini-miloco-http \
  --token-file .cache/miot_oauth.json \
  --cache-dir .cache/miot_cache \
  --camera-snapshot-dir .cache/miot_camera_snapshots \
  --host 127.0.0.1 --port 2324
```

## Notes
- Please avoid adding breaking changes to the MCP tool names.
- If you add new tools, update `README.md` examples accordingly.
