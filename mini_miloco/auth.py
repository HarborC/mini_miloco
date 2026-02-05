#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

try:
    from miot.client import MIoTClient
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root / "miot_kit"))
    from miot.client import MIoTClient


DEFAULT_REDIRECT_URI = "https://mico.api.mijia.tech/login_redirect"


def _parse_code_state(raw: str) -> tuple[Optional[str], Optional[str]]:
    raw = raw.strip()
    if not raw:
        return None, None
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        qs = parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        state = qs.get("state", [None])[0]
        return code, state
    if "code=" in raw:
        qs = parse_qs(raw)
        code = qs.get("code", [None])[0]
        state = qs.get("state", [None])[0]
        return code, state
    return raw, None


async def _run(args: argparse.Namespace) -> int:
    uuid = args.uuid or uuid4().hex
    token_path = Path(args.token_file).expanduser()
    token_path.parent.mkdir(parents=True, exist_ok=True)

    client = MIoTClient(
        uuid=uuid,
        redirect_uri=args.redirect_uri,
        cloud_server=args.cloud_server,
    )
    await client.init_async()
    try:
        auth_url = await client.gen_oauth_url_async()
        print("\nOpen this URL in your browser and finish Xiaomi login:")
        print(auth_url)
        print("\nAfter login, copy the final redirect URL and paste it here.")
        raw = input("Redirect URL (or code): ").strip()
        code, state = _parse_code_state(raw)
        if not code:
            print("No code found. Aborting.")
            return 2

        if not state:
            state = client._oauth_client.state  # pylint: disable=protected-access

        oauth_info = await client.get_access_token_async(code=code, state=state)
        payload = {
            "uuid": uuid,
            "cloud_server": args.cloud_server,
            "redirect_uri": args.redirect_uri,
            "oauth_info": oauth_info.model_dump(exclude_none=True),
            "saved_at": int(time.time()),
        }
        token_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(token_path, 0o600)
        except OSError:
            pass

        print(f"\nSaved token info to: {token_path}")
        print("You can now start the MCP HTTP server with the same token file.")
        return 0
    finally:
        await client.deinit_async()


def main() -> int:
    parser = argparse.ArgumentParser(description="Xiaomi MIoT OAuth helper")
    parser.add_argument("--cloud-server", default="cn", help="Cloud server region, e.g. cn/sg/us/ru/de/i2")
    parser.add_argument("--redirect-uri", default=DEFAULT_REDIRECT_URI, help="OAuth redirect URI")
    parser.add_argument("--token-file", default="config/miot_oauth.json", help="Where to save OAuth info")
    parser.add_argument("--uuid", default=None, help="Device uuid (auto-generated if omitted)")
    args = parser.parse_args()

    try:
        return asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
