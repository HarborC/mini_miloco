import asyncio
import base64
from collections import deque
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse

from . import __version__

DEFAULT_REDIRECT_URI = "https://mico.api.mijia.tech/login_redirect"


def _parse_code_state(raw: str) -> tuple[str | None, str | None]:
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


try:
    from miot.client import MIoTClient
    from miot.cloud import MIoTOAuth2Client
    from miot.mcp import (
        MIoTDeviceMcp,
        MIoTDeviceMcpInterface,
        MIoTManualSceneMcp,
        MIoTManualSceneMcpInterface,
    )
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[1]
    import sys

    sys.path.insert(0, str(repo_root / "miot_kit"))
    from miot.client import MIoTClient
    from miot.cloud import MIoTOAuth2Client
    from miot.mcp import (
        MIoTDeviceMcp,
        MIoTDeviceMcpInterface,
        MIoTManualSceneMcp,
        MIoTManualSceneMcpInterface,
    )


def _load_token_file(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "oauth_info" not in payload:
        raise ValueError("token file missing oauth_info")
    return payload


def _needs_refresh(oauth_info: dict, refresh_window_seconds: int) -> bool:
    expires_ts = oauth_info.get("expires_ts")
    if not isinstance(expires_ts, int):
        return False
    return (expires_ts - int(time.time())) < refresh_window_seconds


async def _interactive_auth(
    *,
    token_path: Path,
    cloud_server: str,
    redirect_uri: str,
    uuid: str | None,
    enable_lan: bool,
) -> dict:
    device_uuid = uuid or uuid4().hex
    oauth_client = MIoTOAuth2Client(
        redirect_uri=redirect_uri,
        cloud_server=cloud_server,
        uuid=device_uuid,
    )
    try:
        auth_url = oauth_client.gen_auth_url(skip_confirm=False)
        print("\nOpen this URL in your browser and finish Xiaomi login:")
        print(auth_url)
        print("\nAfter login, copy the final redirect URL and paste it here.")
        raw = input("Redirect URL (or code): ").strip()
        code, state = _parse_code_state(raw)
        if not code:
            raise RuntimeError("No code provided, aborting.")

        if state and state != oauth_client.state:
            raise RuntimeError("OAuth state mismatch, aborting.")

        oauth_info = await oauth_client.get_access_token_async(code=code)
        payload = {
            "uuid": device_uuid,
            "cloud_server": cloud_server,
            "redirect_uri": redirect_uri,
            "oauth_info": oauth_info.model_dump(exclude_none=True),
            "saved_at": int(time.time()),
        }
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            token_path.chmod(0o600)
        except OSError:
            pass
        return payload
    finally:
        await oauth_client.deinit_async()


async def run_server(
    *,
    token_file: str,
    cache_dir: str,
    refresh_window: int,
    camera_snapshot_dir: str,
    host: str,
    port: int,
    path: str,
    transport: str,
    server_name: str,
    version_name: str,
    cloud_server: str,
    redirect_uri: str,
    uuid: str | None,
    enable_lan: bool,
) -> int:
    token_path = Path(token_file).expanduser()
    pending_auth_url: str | None = None
    pending_auth_state: str | None = None
    pending_auth_uuid: str | None = None
    pending_auth_redirect: str | None = None
    pending_auth_cloud: str | None = None
    payload: dict | None = _load_token_file(token_path) if token_path.exists() else None
    if payload is None:
        print(f"Token file not found: {token_path}")
        print("Authorization required. Visit /auth to authorize.")

    cache_path = Path(cache_dir).expanduser()
    cache_path.mkdir(parents=True, exist_ok=True)

    client: MIoTClient | None = None
    miot_devices_mcp: MIoTDeviceMcp | None = None
    miot_scenes_mcp: MIoTManualSceneMcp | None = None
    auth_lock = asyncio.Lock()
    camera_cache: dict[tuple[str, int], dict] = {}
    camera_cache_events: dict[tuple[str, int], asyncio.Event] = {}
    camera_instances: dict[str, dict] = {}
    auth_required_message = (
        "Authorization required.\n"
        "Steps:\n"
        f"1) Open http://{host}:{port}/auth\n"
        "2) Login, then paste the final redirect URL into the page\n"
        "3) Retry the request\n"
    )

    async def _ensure_client() -> MIoTClient:
        nonlocal payload, client, miot_devices_mcp, miot_scenes_mcp
        async with auth_lock:
            if not token_path.exists():
                payload = None
                raise ToolError(auth_required_message)

            if payload is None:
                payload = _load_token_file(token_path)

            if client is None:
                client = MIoTClient(
                    uuid=payload["uuid"],
                    redirect_uri=payload["redirect_uri"],
                    cloud_server=payload.get("cloud_server", "cn"),
                    oauth_info=payload["oauth_info"],
                    cache_path=str(cache_path),
                    enable_lan=enable_lan,
                )
                await client.init_async()
                miot_devices_mcp = MIoTDeviceMcp(
                    interface=MIoTDeviceMcpInterface(
                        translate_async=client.i18n.translate_async,
                        get_homes_async=client.get_homes_async,
                        get_devices_async=client.get_devices_async,
                        get_prop_async=client.http_client.get_prop_async,
                        set_prop_async=client.http_client.set_prop_async,
                        action_async=client.http_client.action_async,
                    ),
                    spec_parser=client.spec_parser,
                )
                miot_scenes_mcp = MIoTManualSceneMcp(
                    interface=MIoTManualSceneMcpInterface(
                        translate_async=client.i18n.translate_async,
                        get_manual_scenes_async=client.get_manual_scenes_async,
                        trigger_manual_scene_async=client.run_manual_scene_async,
                        send_app_notify_async=client.send_app_notify_once_async,
                    )
                )
                await miot_devices_mcp.init_async()
                await miot_scenes_mcp.init_async()

            if _needs_refresh(payload["oauth_info"], refresh_window):
                try:
                    new_info = await client.refresh_access_token_async(
                        refresh_token=payload["oauth_info"]["refresh_token"]
                    )
                    payload["oauth_info"] = new_info.model_dump(exclude_none=True)
                    payload["saved_at"] = int(time.time())
                    token_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    # force reauth
                    payload = None
                    if client:
                        await client.deinit_async()
                    client = None
                    miot_devices_mcp = None
                    miot_scenes_mcp = None
                    raise ToolError(auth_required_message)

            return client

    async def _get_camera_info(client_ready: MIoTClient, did: str):
        cameras = await client_ready.get_cameras_async()
        if did not in cameras:
            raise ToolError(f"camera not found: {did}")
        return cameras[did]

    async def _get_or_create_camera_instance(
        *,
        client_ready: MIoTClient,
        camera_info,
        pin_code: str | None,
        start_if_needed: bool,
    ):
        state = camera_instances.get(camera_info.did)
        if state is None:
            instance = await client_ready.create_camera_instance_async(camera_info=camera_info)
            state = {
                "instance": instance,
                "started": False,
                "pin_code": pin_code,
                "channels": set(),
                "reg_ids": {},
                "lock": asyncio.Lock(),
            }
            camera_instances[camera_info.did] = state

        if pin_code and state.get("pin_code") and pin_code != state.get("pin_code"):
            raise ToolError("pin_code mismatch for cached camera instance")
        if pin_code and not state.get("pin_code"):
            state["pin_code"] = pin_code

        if start_if_needed and not state["started"]:
            async with state["lock"]:
                if not state["started"]:
                    await state["instance"].start_async(enable_reconnect=True, pin_code=state.get("pin_code"))
                    state["started"] = True

        return state

    async def _ensure_devices_mcp() -> MIoTDeviceMcp:
        await _ensure_client()
        assert miot_devices_mcp is not None
        return miot_devices_mcp

    async def _ensure_scenes_mcp() -> MIoTManualSceneMcp:
        await _ensure_client()
        assert miot_scenes_mcp is not None
        return miot_scenes_mcp
    try:

        async def list_cameras() -> dict:
            client_ready = await _ensure_client()
            cameras = await client_ready.get_cameras_async()
            return {
                did: {
                    "did": info.did,
                    "name": info.name,
                    "online": info.online,
                    "channel_count": info.channel_count,
                    "home_info": f"{info.home_name}-{info.room_name}",
                }
                for did, info in cameras.items()
            }

        async def get_camera_snapshot(
            did: str,
            channel: int = 0,
            timeout: int = 10,
            return_base64: bool = False,
            pin_code: str | None = None,
        ) -> dict:
            client_ready = await _ensure_client()
            camera_info = await _get_camera_info(client_ready, did)
            if channel < 0 or channel >= (camera_info.channel_count or 1):
                raise ToolError(f"invalid channel: {channel}")

            cache_key = (did, channel)
            if cache_key in camera_cache:
                cache = camera_cache[cache_key]
                event = camera_cache_events[cache_key]
                if not cache["frames"]:
                    try:
                        await asyncio.wait_for(event.wait(), timeout=timeout)
                    except asyncio.TimeoutError as exc:
                        raise ToolError(f"snapshot timeout after {timeout}s") from exc
                if not cache["frames"]:
                    raise ToolError("snapshot cache empty")
                data, ts, _ = cache["frames"][-1]
            else:
                state = await _get_or_create_camera_instance(
                    client_ready=client_ready,
                    camera_info=camera_info,
                    pin_code=pin_code,
                    start_if_needed=True,
                )
                instance = state["instance"]

                loop = asyncio.get_running_loop()
                future: asyncio.Future = loop.create_future()

                async def _on_jpg(_did: str, data: bytes, ts: int, _channel: int):
                    if future.done():
                        return
                    future.set_result((data, ts))

                reg_id = await instance.register_decode_jpg_async(callback=_on_jpg, channel=channel, multi_reg=True)
                try:
                    data, ts = await asyncio.wait_for(future, timeout=timeout)
                except asyncio.TimeoutError as exc:
                    raise ToolError(f"snapshot timeout after {timeout}s") from exc
                finally:
                    await instance.unregister_decode_jpg_async(channel=channel, reg_id=reg_id)
                    if not state["channels"]:
                        await instance.stop_async()
                        state["started"] = False

            if return_base64:
                return {
                    "did": did,
                    "channel": channel,
                    "timestamp": ts,
                    "base64": base64.b64encode(data).decode("utf-8"),
                }

            snapshot_dir = Path(camera_snapshot_dir).expanduser()
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            file_path = snapshot_dir / f"camera_{did}_{channel}_{ts}.jpg"
            file_path.write_bytes(data)
            return {
                "did": did,
                "channel": channel,
                "timestamp": ts,
                "file_path": str(file_path),
            }

        async def record_camera_clip(
            did: str,
            channel: int = 0,
            duration: int = 10,
            fps: int = 15,
            pin_code: str | None = None,
        ) -> dict:
            if duration <= 0:
                raise ToolError("duration must be positive")
            if fps <= 0:
                raise ToolError("fps must be positive")

            client_ready = await _ensure_client()
            camera_info = await _get_camera_info(client_ready, did)
            if channel < 0 or channel >= (camera_info.channel_count or 1):
                raise ToolError(f"invalid channel: {channel}")

            cache_key = (did, channel)
            state = await _get_or_create_camera_instance(
                client_ready=client_ready,
                camera_info=camera_info,
                pin_code=pin_code,
                start_if_needed=cache_key not in camera_cache,
            )
            instance = state["instance"]
            if cache_key not in camera_cache and not state["started"]:
                await instance.start_async(enable_reconnect=True, pin_code=pin_code)
                state["started"] = True

            snapshot_dir = Path(camera_snapshot_dir).expanduser()
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            jpg_dir = Path(
                tempfile.mkdtemp(prefix=f"clip_{did}_{channel}_", dir=str(snapshot_dir))
            )
            frame_count = max(1, int(duration * fps))
            frame_futures: list[asyncio.Future] = []

            loop = asyncio.get_running_loop()
            for _ in range(frame_count):
                frame_futures.append(loop.create_future())

            async def _on_jpg(_did: str, data: bytes, ts: int, _channel: int):
                for fut in frame_futures:
                    if not fut.done():
                        fut.set_result((data, ts))
                        break

            reg_id = await instance.register_decode_jpg_async(callback=_on_jpg, channel=channel, multi_reg=True)
            try:
                for idx, fut in enumerate(frame_futures):
                    data, ts = await asyncio.wait_for(fut, timeout=duration + 5)
                    (jpg_dir / f"frame_{idx:05d}_{ts}.jpg").write_bytes(data)
            except asyncio.TimeoutError as exc:
                raise ToolError("record timeout") from exc
            finally:
                await instance.unregister_decode_jpg_async(channel=channel, reg_id=reg_id)
                if cache_key not in camera_cache and not state["channels"]:
                    await instance.stop_async()
                    state["started"] = False

            out_path = snapshot_dir / f"clip_{did}_{channel}_{int(time.time())}.mp4"

            if shutil.which("ffmpeg") is None:
                raise ToolError("ffmpeg is not available. Install imageio-ffmpeg or ffmpeg.")

            input_pattern = str(jpg_dir / "frame_*.jpg")
            if not list(jpg_dir.glob("frame_*.jpg")):
                raise ToolError("no frames captured for recording")
            cmd = [
                "ffmpeg",
                "-y",
                "-r",
                str(fps),
                "-pattern_type",
                "glob",
                "-i",
                input_pattern,
                "-vcodec",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(out_path),
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as exc:
                msg = exc.stderr.decode("utf-8", errors="ignore")
                raise ToolError(f"ffmpeg failed: {msg}\nframes kept at: {jpg_dir}") from exc
            else:
                shutil.rmtree(jpg_dir, ignore_errors=True)

            return {
                "did": did,
                "channel": channel,
                "duration": duration,
                "fps": fps,
                "file_path": str(out_path),
            }

        mcp_server = FastMCP(
            name=server_name,
            instructions="Provides Xiaomi Home device control, manual scenes, and camera tools.",
        )

        async def get_area_info() -> dict:
            device_mcp = await _ensure_devices_mcp()
            return await device_mcp.get_area_info_async()

        async def get_device_classes() -> dict:
            device_mcp = await _ensure_devices_mcp()
            return await device_mcp.get_device_classes_async()

        async def get_devices(area_id: str | None = None, device_class: str | None = None) -> dict:
            device_mcp = await _ensure_devices_mcp()
            return await device_mcp.get_devices_async(area_id=area_id, device_class=device_class)

        async def get_device_spec(did: str) -> dict:
            device_mcp = await _ensure_devices_mcp()
            return await device_mcp.get_device_spec_async(did=did)

        async def send_ctrl_rpc(did: str, iid: str, value):
            device_mcp = await _ensure_devices_mcp()
            return await device_mcp.send_ctrl_rpc_async(did=did, iid=iid, value=value)

        async def send_get_rpc(did: str, iid: str):
            device_mcp = await _ensure_devices_mcp()
            return await device_mcp.send_get_rpc_async(did=did, iid=iid)

        mcp_server.tool(name="get_area_info", description="Get Xiaomi Home area list.")(
            get_area_info
        )
        mcp_server.tool(
            name="get_device_classes",
            description="Get supported Xiaomi Home device class list.",
        )(get_device_classes)
        mcp_server.tool(name="get_devices", description="Get Xiaomi Home device list.")(
            get_devices
        )
        mcp_server.tool(
            name="get_device_spec",
            description="Get Xiaomi Home device SPEC definition.",
        )(get_device_spec)
        mcp_server.tool(
            name="send_ctrl_rpc",
            description="Control a Xiaomi Home device via SPEC instance iid.",
        )(send_ctrl_rpc)
        mcp_server.tool(
            name="send_get_rpc",
            description="Get Xiaomi Home device properties via SPEC instance iid.",
        )(send_get_rpc)

        # Manual scene tools
        async def get_manual_scenes():
            scene_mcp = await _ensure_scenes_mcp()
            return await scene_mcp.get_manual_scenes_async()

        async def trigger_manual_scene(scene_id: str):
            scene_mcp = await _ensure_scenes_mcp()
            return await scene_mcp.trigger_manual_scene_async(scene_id=scene_id)

        async def send_app_notify(content: str):
            scene_mcp = await _ensure_scenes_mcp()
            return await scene_mcp.send_app_notify_async(content=content)

        mcp_server.tool(
            name="get_manual_scenes",
            description="Get Xiaomi Home manual scene list.",
        )(get_manual_scenes)
        mcp_server.tool(
            name="trigger_manual_scene",
            description="Trigger a Xiaomi Home manual scene.",
        )(trigger_manual_scene)
        mcp_server.tool(
            name="send_app_notify",
            description="Send Xiaomi Home app notification.",
        )(send_app_notify)

        # Camera tools
        mcp_server.tool(
            name="list_cameras",
            description="List Xiaomi Home cameras.",
        )(list_cameras)
        mcp_server.tool(
            name="get_camera_snapshot",
            description="Capture a single camera frame and return a file path or base64.",
        )(get_camera_snapshot)
        mcp_server.tool(
            name="record_camera_clip",
            description="Record a short camera clip and return a mp4 path (uses imageio-ffmpeg).",
        )(record_camera_clip)

        async def _start_camera_cache(
            did: str,
            channel: int,
            pin_code: str | None,
            buffer_size: int,
        ) -> dict:
            client_ready = await _ensure_client()
            camera_info = await _get_camera_info(client_ready, did)
            if channel < 0 or channel >= (camera_info.channel_count or 1):
                raise ToolError(f"invalid channel: {channel}")

            state = await _get_or_create_camera_instance(
                client_ready=client_ready,
                camera_info=camera_info,
                pin_code=pin_code,
                start_if_needed=True,
            )
            instance = state["instance"]

            cache_key = (did, channel)
            if cache_key not in camera_cache:
                camera_cache[cache_key] = {
                    "frames": deque(maxlen=buffer_size),
                    "updated_at": None,
                }
                camera_cache_events[cache_key] = asyncio.Event()

                async def _on_jpg(_did: str, data: bytes, ts: int, _channel: int):
                    cache = camera_cache.get(cache_key)
                    if cache is None:
                        return
                    cache["frames"].append((data, ts, time.time()))
                    cache["updated_at"] = time.time()
                    camera_cache_events[cache_key].set()
                    camera_cache_events[cache_key].clear()

                reg_id = await instance.register_decode_jpg_async(
                    callback=_on_jpg,
                    channel=channel,
                    multi_reg=True,
                )
                state["channels"].add(channel)
                state["reg_ids"][channel] = reg_id

            return {
                "did": did,
                "channel": channel,
                "status": "started",
            }

        async def start_camera_cache(
            did: str,
            channel: int = 0,
            pin_code: str | None = None,
            buffer_size: int = 30,
        ) -> dict:
            if buffer_size <= 0:
                raise ToolError("buffer_size must be positive")
            return await _start_camera_cache(
                did=did,
                channel=channel,
                pin_code=pin_code,
                buffer_size=buffer_size,
            )

        async def start_all_camera_cache(
            channel: int = 0,
            pin_code: str | None = None,
            buffer_size: int = 30,
            all_channels: bool = False,
        ) -> dict:
            if buffer_size <= 0:
                raise ToolError("buffer_size must be positive")
            if channel < 0:
                raise ToolError("invalid channel")

            client_ready = await _ensure_client()
            cameras = await client_ready.get_cameras_async()
            results = {}
            for did, camera_info in cameras.items():
                max_channels = camera_info.channel_count or 1
                channels = range(max_channels) if all_channels else [channel]
                per_camera = []
                for ch in channels:
                    if ch < 0 or ch >= max_channels:
                        continue
                    try:
                        res = await _start_camera_cache(
                            did=did,
                            channel=ch,
                            pin_code=pin_code,
                            buffer_size=buffer_size,
                        )
                        per_camera.append(res)
                    except ToolError as exc:
                        per_camera.append({"did": did, "channel": ch, "status": "error", "error": str(exc)})
                results[did] = per_camera
            return {"status": "started_all", "results": results}

        async def stop_camera_cache(
            did: str,
            channel: int = 0,
        ) -> dict:
            cache_key = (did, channel)
            if cache_key not in camera_cache:
                return {"did": did, "channel": channel, "status": "not_running"}

            camera_cache.pop(cache_key, None)
            camera_cache_events.pop(cache_key, None)

            state = camera_instances.get(did)
            if state and channel in state["channels"]:
                reg_id = state["reg_ids"].pop(channel, 0)
                await state["instance"].unregister_decode_jpg_async(channel=channel, reg_id=reg_id)
                state["channels"].discard(channel)
                if not state["channels"]:
                    await state["instance"].stop_async()
                    state["started"] = False

            return {"did": did, "channel": channel, "status": "stopped"}

        async def get_cached_camera_snapshot(
            did: str,
            channel: int = 0,
            max_age: int = 5,
            wait_timeout: int = 0,
            return_base64: bool = False,
        ) -> dict:
            cache_key = (did, channel)
            if cache_key not in camera_cache:
                raise ToolError("camera cache not started")

            cache = camera_cache[cache_key]
            event = camera_cache_events[cache_key]
            now = time.time()
            updated_at = cache.get("updated_at")
            stale = updated_at is None or (now - updated_at) > max_age
            if stale and wait_timeout > 0:
                try:
                    await asyncio.wait_for(event.wait(), timeout=wait_timeout)
                except asyncio.TimeoutError as exc:
                    raise ToolError("cache wait timeout") from exc

            if not cache["frames"]:
                raise ToolError("snapshot cache empty")
            data, ts, _ = cache["frames"][-1]

            if return_base64:
                return {
                    "did": did,
                    "channel": channel,
                    "timestamp": ts,
                    "base64": base64.b64encode(data).decode("utf-8"),
                }

            snapshot_dir = Path(camera_snapshot_dir).expanduser()
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            file_path = snapshot_dir / f"camera_{did}_{channel}_{ts}.jpg"
            file_path.write_bytes(data)
            return {
                "did": did,
                "channel": channel,
                "timestamp": ts,
                "file_path": str(file_path),
            }

        async def get_cached_camera_frames(
            did: str,
            channel: int = 0,
            count: int = 5,
            return_base64: bool = False,
        ) -> dict:
            if count <= 0:
                raise ToolError("count must be positive")
            count = min(count, 50)

            cache_key = (did, channel)
            if cache_key not in camera_cache:
                raise ToolError("camera cache not started")

            cache = camera_cache[cache_key]
            frames = list(cache["frames"])[-count:]
            if not frames:
                raise ToolError("snapshot cache empty")

            if return_base64:
                return {
                    "did": did,
                    "channel": channel,
                    "count": len(frames),
                    "frames": [
                        {
                            "timestamp": ts,
                            "base64": base64.b64encode(data).decode("utf-8"),
                        }
                        for data, ts, _ in frames
                    ],
                }

            snapshot_dir = Path(camera_snapshot_dir).expanduser()
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            out_paths = []
            for data, ts, _ in frames:
                file_path = snapshot_dir / f"camera_{did}_{channel}_{ts}.jpg"
                file_path.write_bytes(data)
                out_paths.append({"timestamp": ts, "file_path": str(file_path)})
            return {"did": did, "channel": channel, "count": len(out_paths), "frames": out_paths}

        mcp_server.tool(
            name="start_camera_cache",
            description="Start a long-running camera connection and cache latest frames.",
        )(start_camera_cache)
        mcp_server.tool(
            name="start_all_camera_cache",
            description="Start long-running cache for all cameras.",
        )(start_all_camera_cache)
        mcp_server.tool(
            name="stop_camera_cache",
            description="Stop the cached camera connection for a channel.",
        )(stop_camera_cache)
        mcp_server.tool(
            name="get_cached_camera_snapshot",
            description="Return latest cached camera frame (file path or base64).",
        )(get_cached_camera_snapshot)
        mcp_server.tool(
            name="get_cached_camera_frames",
            description="Return multiple cached camera frames (file paths or base64).",
        )(get_cached_camera_frames)

        async def _auto_start_all_cameras() -> None:
            while True:
                try:
                    await start_all_camera_cache(channel=0, buffer_size=30, all_channels=False)
                    return
                except ToolError:
                    await asyncio.sleep(5)
                except Exception:
                    await asyncio.sleep(5)

        asyncio.create_task(_auto_start_all_cameras())

        @mcp_server.custom_route("/health", ["GET"], include_in_schema=False)
        async def _health(_request):
            return JSONResponse({"status": "ok"})

        @mcp_server.custom_route("/version", ["GET"], include_in_schema=False)
        async def _version(_request):
            return JSONResponse({"name": version_name, "version": __version__})

        @mcp_server.custom_route("/", ["GET"], include_in_schema=False)
        async def _root(_request):
            body = (
                "<html><body>"
                "<h3>Mini Miloco MCP HTTP</h3>"
                "<ul>"
                f"<li><a href='/health'>/health</a></li>"
                f"<li><a href='/version'>/version</a></li>"
                f"<li><a href='/auth'>/auth</a></li>"
                "</ul>"
                "</body></html>"
            )
            return HTMLResponse(body)

        @mcp_server.custom_route("/auth", ["GET"], include_in_schema=False)
        async def _auth_page(_request):
            nonlocal pending_auth_url, pending_auth_state, pending_auth_uuid, pending_auth_redirect, pending_auth_cloud
            auth_client = None
            try:
                redirect = payload.get("redirect_uri") if payload else redirect_uri
                cloud = payload.get("cloud_server") if payload else cloud_server
                device_uuid = (payload.get("uuid") if payload else None) or uuid or uuid4().hex
                auth_client = MIoTOAuth2Client(
                    redirect_uri=redirect,
                    cloud_server=cloud,
                    uuid=device_uuid,
                )
                pending_auth_url = auth_client.gen_auth_url(skip_confirm=False)
                pending_auth_state = auth_client.state
                pending_auth_uuid = device_uuid
                pending_auth_redirect = redirect
                pending_auth_cloud = cloud
            finally:
                if auth_client:
                    await auth_client.deinit_async()
            body = f"""
            <html>
              <body>
                <h3>Mini Miloco Authorization</h3>
                <p>1) Open this URL and complete login:</p>
                <p><a href="{pending_auth_url}" target="_blank">{pending_auth_url}</a></p>
                <p>2) Paste the final redirect URL below:</p>
                <form method="get" action="/auth/callback">
                  <input type="text" name="url" style="width: 90%;" />
                  <button type="submit">Submit</button>
                </form>
              </body>
            </html>
            """
            return HTMLResponse(body)

        @mcp_server.custom_route("/auth/callback", ["GET"], include_in_schema=False)
        async def _auth_callback(request):
            nonlocal pending_auth_url, payload, pending_auth_state, pending_auth_uuid, pending_auth_redirect, pending_auth_cloud
            url = request.query_params.get("url")
            if not url:
                return PlainTextResponse("Missing ?url= param", status_code=400)

            code, state = _parse_code_state(url)
            if not code:
                return PlainTextResponse("No code found in url", status_code=400)

            device_uuid = pending_auth_uuid or (payload.get("uuid") if payload else None) or uuid or uuid4().hex
            redirect = pending_auth_redirect or (payload.get("redirect_uri") if payload else redirect_uri)
            cloud = pending_auth_cloud or (payload.get("cloud_server") if payload else cloud_server)
            auth_client = MIoTOAuth2Client(
                redirect_uri=redirect,
                cloud_server=cloud,
                uuid=device_uuid,
            )
            try:
                expected_state = pending_auth_state or auth_client.state
                if state and state != expected_state:
                    return PlainTextResponse("OAuth state mismatch", status_code=400)
                oauth_info = await auth_client.get_access_token_async(code=code)
                payload = {
                    "uuid": device_uuid,
                    "cloud_server": cloud,
                    "redirect_uri": redirect,
                    "oauth_info": oauth_info.model_dump(exclude_none=True),
                    "saved_at": int(time.time()),
                }
                token_path.parent.mkdir(parents=True, exist_ok=True)
                token_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                pending_auth_url = None
                pending_auth_state = None
                pending_auth_uuid = None
                pending_auth_redirect = None
                pending_auth_cloud = None
                return PlainTextResponse("Authorization saved. You can retry your request.")
            finally:
                await auth_client.deinit_async()

        await mcp_server.run_http_async(
            transport=transport,
            host=host,
            port=port,
            path=path,
        )
        return 0
    finally:
        if client:
            await client.deinit_async()
