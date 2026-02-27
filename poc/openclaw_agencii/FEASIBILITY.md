# Feasibility Notes

## Goal

Validate that Agency Swarm can collaborate with OpenClaw through OpenResponses while preserving streaming behavior used by Agencii integrations.

## Current PoC status

- Implemented local OpenClaw runtime manager (same container/process unit pattern).
- Implemented strict OpenResponses request normalization proxy.
- Wired Agency Swarm agents to OpenClaw via `OpenAIResponsesModel` and local proxy base URL.
- Added unit coverage for normalization logic and runtime config generation.
- Verified app startup with `OPENCLAW_AUTOSTART=false` and successful responses from:
  - `GET /healthz`
  - `GET /openclaw/health`
- Verified real autostart with latest `openclaw@latest` (`npx -y openclaw@latest gateway --verbose`):
  - runtime starts successfully with generated config
  - `GET /healthz` returns `ok: true`
  - `GET /openclaw/health` returns `ok: true`
  - `POST /openclaw/v1/responses` reaches OpenClaw and returns a model-provider error when provider auth is missing

## Known constraints

- Latest OpenClaw rejects legacy `agent.*` config keys; config must use `agents.defaults.*` and `gateway.mode=local`.
- OpenClaw `/v1/responses` validates request schema strictly.
- OpenAI Agents SDK sends additional fields and shorthand message items that require normalization.
- OpenClaw model execution requires provider auth (for example `OPENAI_API_KEY`) or pre-seeded OpenClaw `auth-profiles.json`.

## Next runtime verification

1. Launch the PoC with provider credentials configured.
2. Call `/openclaw-poc/get_response` and `/openclaw-poc/get_response_stream`.
3. Capture event types and compare against Agencii UI expectations.
4. Only add event-level conversion if stream payload mismatches are observed.
