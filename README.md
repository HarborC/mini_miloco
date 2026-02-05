# Mini Miloco MCP (HTTP)

精简版 Xiaomi MIoT MCP 服务（HTTP），支持设备控制、场景触发、摄像头抓图/录制。

## 功能
- 设备控制：列设备、读写属性、执行动作
- 场景触发：列场景、触发场景、发送米家通知
- 摄像头：列摄像头、抓图、录制短视频（默认 10 秒）

## 快速开始（macOS / 本地）
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
mini-miloco-http --host 127.0.0.1 --port 2324 --path /mcp
```

Linux 建议使用 Docker 方式启动，见下文。

首次调用工具若未授权，请访问：
- `http://127.0.0.1:2324/auth`

授权文件默认保存到：
- `~/.mini-miloco/miot_oauth.json`

## Claude Code 配置（HTTP）
```bash
claude mcp add xiaomi-miot --transport http http://127.0.0.1:2324/mcp
```

## 启动
### 本地脚本（macOS / 本地）
```bash
source .venv/bin/activate
bash scripts/start.sh
```

常用参数：
- `bash scripts/start.sh --autostart` 生成开机自启
- `bash scripts/start.sh --autostart-uninstall` 移除自启
- `bash scripts/start.sh --add-claude` 添加 Claude MCP 配置

## Linux（Docker）
先安装 Docker（可参考 `xiaomi-miloco/docs/environment-setup-linux_zh-Hans.md`）。

在 `mini_miloco` 目录下构建并启动：
```bash
docker compose up -d --build
```

查看日志：
```bash
docker compose logs -f
```

授权与状态页面：
- `http://127.0.0.1:2324/`
- `http://127.0.0.1:2324/auth`

数据会持久化到：
- `~/.mini-miloco`

说明：
- Docker 默认禁用 LAN discovery（`--disable-lan`）。如需局域网发现，可在 `docker-compose.yml` 中改为 `--enable-lan`，并考虑使用 `network_mode: host`。

## 状态与授权
- 状态页：`http://127.0.0.1:2324/`
- 授权页：`http://127.0.0.1:2324/auth`
- 健康检查：`http://127.0.0.1:2324/health`
- 版本信息：`http://127.0.0.1:2324/version`

## 说明
- macOS 默认关闭局域网发现；如需开启使用 `--enable-lan`。
- 摄像头录制依赖 `imageio-ffmpeg`。

## License
见 `LICENSE.md` 与 `NOTICE.md`。
