# OpenClaw ↔ Agencii.ai Integration Pitch (Approval Draft)

Date: February 27, 2026
Owner: Agencii.ai Engineering

## 1) Executive Summary

We propose integrating OpenClaw into Agencii.ai as a dedicated runtime, while keeping OpenAI Open Responses as the main standard across our stack.

This gives us:

- OpenClaw capabilities inside Agencii deployments.
- A standard API shape (Open Responses) for future portability.
- A controlled rollout path with clear acceptance checks before production use.

## 2) Business Problem

Today, adding a new agent runtime can create vendor lock-in and extra custom translation logic.
We need a path that:

- Works with Agencii deployment patterns.
- Preserves Open Responses compatibility.
- Avoids custom event conversion unless real incompatibility is proven.

## 3) Proposed Solution

Deploy one new OpenClaw-backed service unit on Agencii.ai:

- Agency Swarm FastAPI service as the app entrypoint.
- OpenClaw gateway as a managed subprocess in the same deployment unit.
- Open Responses proxy endpoint exposed by the app.
- Minimal request normalization only where OpenClaw schema is stricter.

## 4) Standards Decision (Important)

Primary standard: **OpenAI Open Responses**.

Policy:

- Default to Open Responses payloads/events as-is.
- Add format conversion only when we observe concrete mismatch in runtime behavior.
- Keep conversion layer small, explicit, and test-covered.

## 5) Feasibility Findings

Based on implementation and runtime validation against latest sources:

- Branch baseline is latest `origin/main` from Agency Swarm (`bd7ab3cf`, February 27, 2026).
- OpenClaw can be launched in-process by the Agencii app runtime.
- OpenClaw `/v1/responses` is reachable through the proxy path.
- Strict schema differences are manageable with a small normalization step.

Key technical constraint discovered:

- Latest OpenClaw rejects legacy `agent.*` config keys; config must use `agents.defaults.*` and `gateway.mode=local`.

Operational constraint:

- Model provider credentials are required for non-mock completions (for example `OPENAI_API_KEY` or OpenClaw auth profiles).

## 6) Proposed Scope (Phase 1)

In scope:

- Deployable OpenClaw-backed PoC service on Agencii platform.
- Health endpoints and runtime lifecycle management.
- Open Responses request normalization for known strict fields.
- Validation of sync + streaming behavior for Agencii UI paths.

Out of scope:

- Broad event-format rewriting before mismatch is observed.
- Multi-runtime routing policy changes outside this PoC.
- Production SLO commitments before approval and soak testing.

## 7) High-Level Architecture

1. Client calls Agencii endpoint (`/openclaw-poc/*` or `/openclaw/v1/responses`).
2. Agency Swarm handles orchestration and forwards Responses payloads.
3. Proxy normalizes only strict incompatibilities.
4. OpenClaw gateway executes the request via `/v1/responses`.
5. Response streams back through the same path.

## 8) Risks and Mitigations

1. OpenClaw config schema drift.
   Mitigation: generate schema-compliant config at startup and test migration behavior.
2. Provider auth gaps at deploy time.
   Mitigation: required env checklist + health/readiness verification.
3. Streaming event mismatch with Agencii UI.
   Mitigation: run capture tests first; add conversion only for proven mismatches.
4. Cold start delays when using `npx openclaw@latest`.
   Mitigation: prefer preinstalled OpenClaw in container image for production rollout.

## 9) Success Criteria

Approval should require these checks:

- Service starts and reports healthy.
- `/openclaw/v1/responses` works with valid provider auth.
- `/openclaw-poc/get_response` and `/openclaw-poc/get_response_stream` both function.
- No event conversion added unless a reproducible mismatch exists.
- Deployment docs include required env vars and runtime constraints.

## 10) Approval Request

Please approve the following:

1. Use Open Responses as the default standard for this integration.
2. Keep event conversion as conditional (only if proven needed).
3. Proceed with controlled Phase 1 rollout on Agencii.ai using this architecture.
4. Move to production hardening only after Phase 1 acceptance tests pass.
