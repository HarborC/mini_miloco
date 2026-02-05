# Contributing

Thanks for your interest in Mini Miloco.

## Development Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Local Run
```bash
mini-miloco-auth --cloud-server cn
mini-miloco-http --token-file config/miot_oauth.json --host 127.0.0.1 --port 9000
```

## Notes
- Please avoid adding breaking changes to the MCP tool names.
- If you add new tools, update `README.md` examples accordingly.
