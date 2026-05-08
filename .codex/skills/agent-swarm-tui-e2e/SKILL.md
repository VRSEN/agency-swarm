---
name: agent-swarm-tui-e2e
description: Use when adding, fixing, reviewing, or manually QAing Agent Swarm terminal TUI behavior in agentswarm-cli. Derives the canonical harness, environment isolation, evidence expectations, and manual gaps from e2e/agent-swarm-tui tests.
---

# Agent Swarm TUI E2E

Use this skill for Agent Swarm terminal UI changes, especially Run mode, `/agents`, `/auth`, `/connect`, handoffs, queued prompts, attachment-visible flows, launcher startup, and release QA that needs terminal evidence.

## Evidence Sources

Read only the relevant bounded sections before acting:

- `e2e/agent-swarm-tui/terminal-tui.test.ts` for covered user flows and assertions.
- `e2e/agent-swarm-tui/harness.ts` for the canonical PTY harness, environment isolation, fake Agency Protocol server, and terminal screen model.
- `e2e/agent-swarm-tui/QA_COVERAGE.md` for automated coverage and manual gaps.
- `USER_FLOWS.md` for release QA flow intent when a change affects a listed fork flow.

If these files are missing or do not cover the requested behavior enough to build a reliable test or QA step, stop and escalate instead of inventing a workflow.

## Canonical Harness Facts

- Start the real terminal UI through `packages/opencode/src/index.ts` with Bun and browser conditions.
- Use a PTY sized `100` columns by `30` rows.
- Use `TERM=xterm-256color` and `CI=1`.
- Isolate `HOME`, `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `OPENCODE_CONFIG_DIR`, `OPENCODE_TEST_HOME`, and `OPENCODE_TEST_MANAGED_CONFIG_DIR` under a temporary root.
- Disable unrelated runtime behavior with `OPENCODE_DISABLE_AUTOUPDATE=true`, `OPENCODE_DISABLE_DEFAULT_PLUGINS=true`, `OPENCODE_DISABLE_MODELS_FETCH=true`, `OPENCODE_DISABLE_PROJECT_CONFIG=true`, and `OPENCODE_PURE=1`.
- Use the fixture models file at `packages/opencode/test/tool/fixtures/models-api.json`.
- Scrub parent provider credentials before the TUI process starts.
- Drive the UI with PTY input, then assert on both normalized screen text and raw history tail.
- Close the PTY with Ctrl-C, then `SIGTERM`, then `SIGKILL` only if needed.

## Agency Swarm Protocol Fixture

For deterministic Agent Swarm TUI tests, prefer the in-process Bun server pattern from `harness.ts`:

- Serve `/openapi.json`, `/<agency>/get_metadata`, `/<agency>/get_response_stream`, and `/<agency>/cancel_response_stream`.
- Capture request bodies for assertions.
- Stream SSE events with `meta`, `data`, `messages`, and `end` events as the tested behavior requires.
- For handoff behavior, use the TUI-demo-shaped fixture from `harness.ts`: `TuiDemoAgency`, `UserSupportAgent`, `MathAgent`, and a `transfer_to_math_agent` tool event followed by an `agent_updated_stream_event`.

## Test Expectations

- Add or extend a terminal E2E test when a change affects a listed Agent Swarm TUI user flow.
- Prefer extending `e2e/agent-swarm-tui/terminal-tui.test.ts` and `harness.ts` over adding a new harness.
- Prove routing behavior at the protocol boundary by asserting the captured request body, not only rendered text.
- For handoffs, assert the next turn routes to the transferred agent and does not replay fork-only internal markers such as `handoff_output_item`.
- For slash commands and pickers, assert user-visible text and hidden native commands when the flow depends on filtering.
- For launcher cold-start, use the documented manual gap unless the test can avoid live Python package installs and live credentials.

## Commands

Run focused TUI E2E from `packages/opencode`:

```sh
bun test --timeout 180000 --max-concurrency=1 ../../e2e/agent-swarm-tui
```

Run package typecheck after code changes:

```sh
bun run typecheck
```

Use the package script for CI-shaped TUI E2E when needed:

```sh
bun run test:agentswarm:e2e
```

## Visual Evidence

When the bug or review target is visual, capture evidence from the same canonical PTY size or state the exact difference. Prefer a real screenshot or a rendered terminal frame over prose. Do not use visual evidence as a substitute for protocol-boundary assertions when routing or payload behavior is the risk.
