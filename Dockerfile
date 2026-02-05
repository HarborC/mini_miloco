FROM ubuntu:24.04

WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE.md NOTICE.md requirements.txt /app/
COPY mini_miloco /app/mini_miloco
COPY miot_kit /app/miot_kit

RUN python3 -m pip install --upgrade pip setuptools wheel \
    && python3 -m pip install .

ENV MINI_MILOCO_STATE_DIR=/data
ENV MINI_MILOCO_TOKEN_FILE=/data/miot_oauth.json

VOLUME ["/data"]
EXPOSE 2324

ENTRYPOINT ["mini-miloco-http"]
CMD ["--host", "0.0.0.0", "--port", "2324", "--path", "/mcp", "--token-file", "/data/miot_oauth.json", "--cache-dir", "/data/miot_cache", "--camera-snapshot-dir", "/data/miot_camera_snapshots", "--disable-lan"]
