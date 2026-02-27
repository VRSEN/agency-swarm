# OpenClaw ↔ Agencii.ai PoC (Inside `agency-swarm` Repo)

## Summary
Build a runnable PoC in this repo that proves Agency Swarm can call OpenClaw as an external agent backend, stream events into current Agencii-style FastAPI flows, and deploy with starter-template conventions.
We will try **no conversion first**. If compatibility breaks, we add a thin OpenResponses adapter (request first, event only if needed).

## Confirmed Inputs
- OpenClaw source target: `openclaw/openclaw` (`main`, latest seen `b044c149c11652bae9cb0c5d55abc6ffaa024268`, dated 2026-02-26).
- Deploy-pack base: `agency-ai-solutions/agency-starter-template` (`main`, latest seen `14920a92df83b2d963b2802f2f12ff17db542daf`).
- PoC location: inside current repo.
- Scope: local runnable proof + deploy pack.
- Preference: keep OpenAI/OpenResponses standard; convert only when required.
- Runtime constraint: same container, ideally single app process entrypoint.
- Storage target: `/mnt` for persistence in Agencii.

## Why Adapter Is Likely Needed
Direct `OpenAIResponsesModel` calls currently include payload shapes OpenClaw strict schema does not accept (observed SDK request keys include `include`, plus shorthand list input without `type`).
So plan includes a hard gate:
1. Try direct OpenClaw call path first.
2. If it fails on schema mismatch, enable request normalization adapter.
3. Keep SSE passthrough unless event mismatch is observed.

## Implementation Plan

## 1. Create PoC Workspace and Pin References
1. Create `/Users/nick/.codex/worktrees/7de2/agency-swarm/poc/openclaw_agencii/`.
2. Clone OpenClaw into `/Users/nick/.codex/worktrees/7de2/agency-swarm/poc/openclaw_agencii/references/openclaw`.
3. Clone starter template into `/Users/nick/.codex/worktrees/7de2/agency-swarm/poc/openclaw_agencii/references/agency-starter-template`.
4. Add `/Users/nick/.codex/worktrees/7de2/agency-swarm/poc/openclaw_agencii/REFERENCES.lock.md` with pinned SHAs and clone date.

## 2. Build PoC App from Starter Template Pattern
1. Create app root at `/Users/nick/.codex/worktrees/7de2/agency-swarm/poc/openclaw_agencii/app/` using starter-template structure (`agency.py`, `main.py`, `requirements.txt`, `Dockerfile`, `.env.template`).
2. Keep FastAPI bootstrap pattern aligned with current framework docs in:
`/Users/nick/.codex/worktrees/7de2/agency-swarm/src/agency_swarm/integrations/fastapi.py` and
`/Users/nick/.codex/worktrees/7de2/agency-swarm/docs/additional-features/fastapi-integration.mdx`.

## 3. Add OpenClaw Runtime Manager (Same Container Flow)
1. Add `/Users/nick/.codex/worktrees/7de2/agency-swarm/poc/openclaw_agencii/app/openclaw_runtime.py`.
2. Startup behavior:
- Ensure `/mnt/openclaw` exists.
- Write OpenClaw config at `/mnt/openclaw/openclaw.json` with `gateway.http.endpoints.responses.enabled=true`.
- Start OpenClaw gateway subprocess bound to loopback (for example `127.0.0.1:18789`) with token auth.
3. Shutdown behavior:
- Graceful terminate OpenClaw subprocess.
- Force kill on timeout.
4. Expose a local health check utility for gateway readiness (used by app startup and smoke tests).

## 4. Add OpenResponses Proxy (Only If Direct Call Fails)
1. Add `/Users/nick/.codex/worktrees/7de2/agency-swarm/poc/openclaw_agencii/app/openclaw_proxy.py`.
2. Mount proxy endpoint in same FastAPI app (example prefix `/openclaw/v1/responses`).
3. Request normalization rules:
- Drop unsupported SDK fields (`include`, `conversation`, `prompt`, `parallel_tool_calls`, `text`, `prompt_cache_retention`).
- Normalize `input` list items without `type` into `{type:"message", role, content}`.
- Normalize content parts to OpenClaw-accepted part types.
- Strip tool definitions to strict OpenClaw subset.
- Preserve allowed OpenResponses fields (`model`, `input`, `instructions`, `tools`, `tool_choice`, `stream`, `max_output_tokens`, `user`, etc.).
4. Streaming behavior:
- Pass through SSE events as-is by default.
- Preserve `event:` + `data:` framing and terminal `[DONE]`.
5. Event conversion fallback:
- Add optional mapping only if runtime test shows unsupported event payloads for Agency Swarm consumers.

## 5. Wire Agency Swarm Agents to OpenClaw
1. In PoC `agency.py`, define:
- One orchestrator/coordinator agent.
- One OpenClaw-backed specialist agent using model alias like `openclaw:main`.
2. Use current communication flow tooling (`send_message`) so Agency Swarm agent collaboration includes OpenClaw-backed turns.
3. Configure OpenAI client base URL to local proxy path (if adapter enabled) or direct OpenClaw `/v1` (if direct compatibility passes).

## 6. Make Deploy Pack Agencii-Ready
1. Dockerfile:
- Base from starter-template style Python image.
- Add Node 22 runtime.
- Install OpenClaw CLI/runtime.
- Install Python deps for Agency Swarm FastAPI app.
2. Environment defaults:
- `OPENCLAW_HOME=/mnt/openclaw`
- `OPENCLAW_CONFIG_PATH=/mnt/openclaw/openclaw.json`
- `OPENCLAW_STATE_DIR=/mnt/openclaw/state`
- `MNT_DIR=/mnt`
- Agency app token + OpenClaw token envs.
3. Entrypoint:
- Single Python app entrypoint that starts OpenClaw child process and FastAPI server.
4. Add deployment runbook:
`/Users/nick/.codex/worktrees/7de2/agency-swarm/poc/openclaw_agencii/DEPLOY_AGENCII.md`
with required env vars, health checks, and `/mnt` persistence notes.

## 7. Feasibility Evaluation Deliverables
1. Add `/Users/nick/.codex/worktrees/7de2/agency-swarm/poc/openclaw_agencii/FEASIBILITY.md`.
2. Include:
- Direct path result (pass/fail + exact error if fail).
- Adapter path result (pass/fail).
- Event compatibility matrix (`get_response_stream` event types observed vs expected).
- Risks and decisions for next iteration (Codex/Claude/OpenCode external connectors).

## Public API / Interface Changes
1. Core framework: **none required for PoC v1** (keeps risk low).
2. PoC app interfaces added:
- OpenClaw runtime manager interface (`start()`, `stop()`, `health()`).
- OpenResponses proxy adapter interface (`normalize_request()`, optional `normalize_event()`).
3. Optional phase-2 extraction (after PoC proves stable):
- move proxy utilities into reusable `agency_swarm.integrations` module.

## Test Cases and Scenarios
1. Adapter unit tests:
- request key filtering.
- input item normalization.
- tool schema normalization.
2. Proxy integration tests with OpenClaw-like stub:
- non-stream request returns valid response resource.
- stream request forwards SSE frames and `[DONE]`.
3. Agency integration tests:
- `get_response` through OpenClaw path.
- `get_response_stream` through OpenClaw path with event assertions.
- `send_message` flow where one recipient is OpenClaw-backed.
4. Startup/runtime tests:
- OpenClaw subprocess starts and health-check passes.
- shutdown cleanup works.
5. Deploy-pack smoke:
- container starts with `/mnt` mounted.
- persistence files appear under `/mnt/openclaw` and app state under `/mnt`.

## Validation Commands (Implementation Phase)
1. Focused tests first (new/changed test files).
2. `make format`
3. `make check`
4. Run PoC smoke script under `poc/openclaw_agencii` (local non-interactive).
5. If keys available, run one real OpenClaw end-to-end stream smoke test.

## Assumptions and Defaults
1. Use public `openclaw/openclaw` and `agency-starter-template` repos as canonical references.
2. `agent-swarm-cli` private repo is not available from this environment; not blocked for this PoC.
3. `/mnt` exists and is writable in Agencii runtime.
4. OpenClaw provider/model auth is provided by env/secrets at deploy time.
5. No OpenClaw source modification is planned; compatibility is achieved by config and adapter layer if needed.
6. Event conversion is deferred unless a real mismatch is observed in stream-contract tests.
