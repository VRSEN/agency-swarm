# OpenClaw ↔ Agencii.ai PoC

This PoC runs OpenClaw and an Agency Swarm FastAPI service in one deployment unit.

Key behavior:

- Starts a local OpenClaw gateway process on startup.
- Exposes Agency Swarm endpoints at `/openclaw-poc/*`.
- Proxies OpenResponses traffic to OpenClaw via `/openclaw/v1/responses`.
- Normalizes strict request fields so OpenAI Agents SDK payloads are accepted by OpenClaw.

## Quick Start

```bash
cd poc/openclaw_agencii
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.template .env
python main.py
```

Endpoints:

- `POST /openclaw-poc/get_response`
- `POST /openclaw-poc/get_response_stream`
- `POST /openclaw/v1/responses` (OpenClaw proxy)
- `GET /healthz`

## Full Delegation E2E Test

Run the live end-to-end delegation test (opt-in):

```bash
RUN_OPENCLAW_E2E=1 uv run pytest poc/openclaw_agencii/tests/test_e2e_delegation.py -q
```

Requirements:

- Root repo `.env` contains `OPENAI_API_KEY`.
- `openclaw` or `npx` is available in `PATH`.

## Notes

- `references/` contains local clones for exploration and is git-ignored.
- Persistent runtime data is written under `/mnt/openclaw` by default.
- If `openclaw` is not installed, set `OPENCLAW_GATEWAY_COMMAND` to an `npx` command.
- The generated OpenClaw config uses latest schema (`agents.defaults.*`, `gateway.mode=local`) and enables `gateway.http.endpoints.responses.enabled=true`.
- Runtime auto-loads `OPENAI_API_KEY` from repository `.env` files (current repo root, then linked git worktrees) and injects it into the OpenClaw subprocess.
- Provider credentials are required for real model runs (for example `OPENAI_API_KEY`), otherwise `/openclaw/v1/responses` returns an OpenClaw provider-auth error.
