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

### Worker-facing agent wrapper

Use `OpenClawAgent` when Agency Swarm should delegate work into an OpenClaw worker:

```python
from agency_swarm.agents import OpenClawAgent

openclaw_worker = OpenClawAgent(
    name="OpenClawWorker",
    description="Handles OpenClaw-native work.",
    instructions="Return the result to the calling agent.",
)
```

`OpenClawAgent` configures the model automatically by default and is receive-only
in `communication_flows`. It can receive delegated work, but it cannot be used
as the sender in Agency Swarm handoffs or `send_message` routes. Raw `/v1`
gateways default to the upstream provider model, while `/openclaw/v1` keeps the
public alias path. When a remote server expects a different model id, pass that
string with the agent's `model=` argument. When pointing at another Agency
Swarm worker, pass its `api_key=` explicitly unless you are using the same
in-process proxy.

### Why `openclaw:main` exists

OpenClaw itself does not expose a native model id like OpenAI does.
Agency Swarm still needs a stable model string for the Responses model client, so the integration uses an internal alias: `openclaw:main`.

Runtime mapping:

- External alias used by Agency Swarm agent config: `openclaw:main`
- Upstream provider model used by OpenClaw gateway: `OPENCLAW_PROVIDER_MODEL` (default `openai/gpt-5.4`)

When the proxy receives `model=openclaw:main`, it rewrites that value to the configured provider model before forwarding upstream.

### Runtime defaults and persistence

For Agent Swarm deploys, set:

- `OPENCLAW_HOME=/app/mnt/openclaw`
- `OPENCLAW_PORT=18789`

From `OPENCLAW_HOME`, the integration derives:

- `OPENCLAW_STATE_DIR=<OPENCLAW_HOME>/state`
- `OPENCLAW_CONFIG_PATH=<OPENCLAW_HOME>/openclaw.json`
- `OPENCLAW_LOG_PATH=<OPENCLAW_HOME>/logs/openclaw-gateway.log`
- `agents.defaults.workspace=<OPENCLAW_HOME>/workspace` in the generated `openclaw.json`

In Agent Swarm's file browser, the mounted volume is visible at `/app/mnt/openclaw`.
OpenClaw workspace files should appear at `/app/mnt/openclaw/workspace`.

If an older deploy already has files under the legacy `.openclaw/workspace` path, the integration migrates that workspace to the cleaner path when it is safe to do so.

Generated gateway config enables:

- `gateway.http.endpoints.responses.enabled=true`

Worker mode is available when the runtime is used as a delegated OpenClaw worker:

- `OPENCLAW_TOOL_MODE=worker`

Worker mode disables the OpenClaw messaging paths that compete with Agency Swarm
delegation:

- `message`
- `sessions_send`
- `sessions_spawn`

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

### Tool extension boundary

The OpenClaw proxy can forward Open Responses function schemas, but the clean
OpenClaw-native extension paths are still:

- OpenClaw plugin tools via `api.registerTool(...)`
- MCP servers exposed to OpenClaw
- OpenClaw tool policy config (`tools.allow`, `tools.deny`, `tools.byProvider`)

Do not treat ordinary Agency Swarm Python tools as the main extension story for
`OpenClawAgent`.
