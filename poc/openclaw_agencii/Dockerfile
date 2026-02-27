FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MNT_DIR=/mnt \
    OPENCLAW_DATA_DIR=/mnt/openclaw \
    OPENCLAW_STATE_DIR=/mnt/openclaw/state \
    OPENCLAW_CONFIG_PATH=/mnt/openclaw/openclaw.json \
    OPENCLAW_LOG_PATH=/mnt/openclaw/openclaw-gateway.log

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g openclaw@latest \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-u", "main.py"]
