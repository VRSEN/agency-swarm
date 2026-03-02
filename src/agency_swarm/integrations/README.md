# Integrations Technical Reference

This file documents technical details for framework integrations that are too low-level for end-user deployment docs.

## OpenClaw Integration

### What the helper does

`attach_openclaw_to_fastapi(app, config=None)` is the runtime mount helper.
It is needed because it does three things together:

1. Mounts proxy routes:
   - `POST /openclaw/v1/responses`
   - `GET /openclaw/health`
2. Registers OpenClaw startup/shutdown lifecycle on the FastAPI app.
3. Stores runtime/config on `app.state` for health and diagnostics.

Without this helper, the OpenClaw proxy endpoints are not mounted and the OpenClaw runtime process is not managed by the app.

### Why `openclaw:main` exists

OpenClaw itself does not expose a native model id like OpenAI does.
Agency Swarm still needs a stable model string for the Responses model client, so the integration uses an internal alias: `openclaw:main`.

Runtime mapping:

- External alias used by Agency Swarm agent config: `openclaw:main`
- Upstream provider model used by OpenClaw gateway: `OPENCLAW_PROVIDER_MODEL` (default `openai/gpt-5-mini`)

When the proxy receives `model=openclaw:main`, it rewrites that value to the configured provider model before forwarding upstream.

### Runtime defaults and persistence

Default runtime paths are designed for persistent E2B storage:

- `OPENCLAW_HOME=/mnt/openclaw`
- `OPENCLAW_STATE_DIR=/mnt/openclaw/state`
- `OPENCLAW_CONFIG_PATH=/mnt/openclaw/openclaw.json`
- `OPENCLAW_LOG_PATH=/mnt/openclaw/logs/openclaw-gateway.log`
- `OPENCLAW_PORT=18789`

Generated gateway config enables:

- `gateway.http.endpoints.responses.enabled=true`

### End-to-end app wiring example

```python
from agency import create_agency
from agency_swarm.integrations.fastapi import run_fastapi
from agency_swarm.integrations.openclaw import attach_openclaw_to_fastapi

app = run_fastapi(
    agencies={"openclaw": create_agency},
    app_token_env="APP_TOKEN",
    return_app=True,
)
if app is None:
    raise RuntimeError("FastAPI app failed to start")

attach_openclaw_to_fastapi(app)
```

### Current template scope

The starter template currently ships with one OpenClaw-backed agent by default.
It does not ship a pre-built multi-agent delegation topology.

If you want collaboration/delegation, you can add more Agency Swarm agents and handoff rules on top of this integration.
