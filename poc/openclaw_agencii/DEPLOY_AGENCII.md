# Deploy on Agencii (PoC)

## Required env vars

- `APP_TOKEN`
- `OPENCLAW_GATEWAY_TOKEN`
- Provider credentials used by OpenClaw model backend (for example `OPENAI_API_KEY`) or pre-seeded OpenClaw auth profiles under `OPENCLAW_STATE_DIR/agents/main/agent/auth-profiles.json`

## Recommended env vars

- `MNT_DIR=/mnt`
- `OPENCLAW_DATA_DIR=/mnt/openclaw`
- `OPENCLAW_STATE_DIR=/mnt/openclaw/state`
- `OPENCLAW_CONFIG_PATH=/mnt/openclaw/openclaw.json`
- `OPENCLAW_LOG_PATH=/mnt/openclaw/openclaw-gateway.log`

## Health checks

- HTTP liveness: `GET /healthz`
- Agency metadata: `GET /openclaw-poc/get_metadata`
- OpenClaw proxy ping: `GET /openclaw/health`

## Runtime model

- Single app container process (`python main.py`)
- OpenClaw gateway launched as subprocess by FastAPI startup hook
- OpenClaw persistent files and logs stored under `/mnt/openclaw`
