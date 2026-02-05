# Mini Miloco MCP

Xiaomi MIoT MCP 服务，支持设备控制、场景触发、摄像头抓图/录制。

## 功能
- 设备控制：列设备、读写属性、执行动作
- 场景触发：列场景、触发场景、发送米家通知
- 摄像头：列摄像头、抓图、录制短视频（默认 10 秒）

## 系统依赖
```bash
bash scripts/setup_deps.sh
```

## 启动脚本（推荐）
```bash
bash scripts/start.sh
```
其中 :

macOS：自动使用 venv 并通过 tmux 后台运行。
```bash
# 查看输出/交互
tmux attach -t mini-miloco
```

Linux：自动使用 Docker Compose。
```bash
# 查看输出/交互
docker compose logs -f
```

数据持久化目录：
- `./.cache`

## 授权与状态
首次调用工具若未授权，请访问：
- `http://127.0.0.1:2324/auth`

授权文件默认保存到：
- `./.cache/miot_oauth.json`

状态与健康检查：
- `http://127.0.0.1:2324/`
- `http://127.0.0.1:2324/health`
- `http://127.0.0.1:2324/version`


## Claude Code MCP 配置
```bash
claude mcp add xiaomi-miot --transport http http://127.0.0.1:2324/mcp
```

## macOS 本地运行（venv）
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
mkdir -p .cache
mini-miloco-http \
  --host 127.0.0.1 --port 2324 --path /mcp \
  --token-file .cache/miot_oauth.json \
  --cache-dir .cache/miot_cache \
  --camera-snapshot-dir .cache/miot_camera_snapshots
```


## Linux Docker 运行
先安装 Docker（可参考 `xiaomi-miloco/docs/environment-setup-linux_zh-Hans.md`）。

在 `mini_miloco` 目录下构建并启动（首次需要 build，之后代码更新无需重建）：
```bash
docker compose up -d --build
```

代码更新后直接重启即可：
```bash
docker compose restart
```

查看日志：
```bash
docker compose logs -f
```








## License
见 `LICENSE.md` 与 `NOTICE.md`。
