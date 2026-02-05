#!/usr/bin/env python3
import argparse
import asyncio
import platform
import sys

from .server import run_server


def main() -> int:
    parser = argparse.ArgumentParser(description="MIoT MCP HTTP server (devices/scenes/cameras)")
    parser.add_argument(
        "--token-file",
        default="~/.mini-miloco/miot_oauth.json",
        help="OAuth token file",
    )
    parser.add_argument(
        "--cache-dir",
        default="~/.mini-miloco/miot_cache",
        help="Cache directory for MIoT specs",
    )
    parser.add_argument("--refresh-window", type=int, default=3600, help="Refresh token if expiring within seconds")
    parser.add_argument(
        "--camera-snapshot-dir",
        default="~/.mini-miloco/miot_camera_snapshots",
        help="Directory to write camera snapshots",
    )
    parser.add_argument("--cloud-server", default="cn", help="Cloud server region, e.g. cn/sg/us/ru/de/i2")
    parser.add_argument("--redirect-uri", default="https://mico.api.mijia.tech/login_redirect", help="OAuth redirect URI")
    parser.add_argument("--uuid", default=None, help="Device uuid (auto-generated if omitted)")
    parser.add_argument(
        "--disable-lan",
        action="store_true",
        default=platform.system() == "Darwin",
        help="Disable LAN discovery (default on macOS)",
    )
    parser.add_argument("--enable-lan", action="store_true", help="Force enable LAN discovery")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP listen host")
    parser.add_argument("--port", type=int, default=2324, help="HTTP listen port")
    parser.add_argument("--path", default="/mcp", help="HTTP base path")
    args = parser.parse_args()
    enable_lan = not args.disable_lan
    if args.enable_lan:
        enable_lan = True

    try:
        return asyncio.run(
            run_server(
                token_file=args.token_file,
                cache_dir=args.cache_dir,
                refresh_window=args.refresh_window,
                camera_snapshot_dir=args.camera_snapshot_dir,
                host=args.host,
                port=args.port,
                path=args.path,
                transport="http",
                server_name="Xiaomi MIoT MCP (http)",
                version_name="mini-miloco-http",
                cloud_server=args.cloud_server,
                redirect_uri=args.redirect_uri,
                uuid=args.uuid,
                enable_lan=enable_lan,
            )
        )
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
