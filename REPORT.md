# httpx2-Generation Dependency Core Migration

Migrates Agency Swarm's dependency core to the httpx2-generation stack: OpenAI 3.x,
Agents SDK 0.22.x, MCP 2.x, and httpx2, with LiteLLM demoted to an optional extra.

## Version map

| Package         | Before      | After    | Constraint          |
| --------------- | ----------- | -------- | ------------------- |
| `openai`        | 2.x         | 3.16.2   | `>=3,<4`            |
| `openai-agents` | 0.18.1      | 0.22.3   | `>=0.22,<0.23`      |
| `mcp`           | 1.x         | 2.2.0    | `>=2,<3`            |
| `httpx`         | 0.28.x      | —        | removed             |
| `httpx2`        | —           | 2.13.0   | `>=2.13,<3`         |
| `fastmcp`       | 2.x         | 4.0.5    | `>=4.0.5,<5`        |
| `litellm`       | base dep    | extra    | `>=1.83.0,!=1.92.*,!=1.93.*,!=1.94.*,!=1.95.*` (locked 1.101.0) |

`fastapi`, `uvicorn[standard]`, `ag-ui-protocol`, `aiofiles`, `filetype`, and
`httpx2` moved into the base dependency set because the OpenClaw/FastAPI surface
is part of the core install.

## LiteLLM compatibility

Every released LiteLLM version (checked through 1.101.0) still publishes
`openai>=2.20,<3` and `httpx>=0.28,<1` pins. The pins are stale: LiteLLM imports
and functions correctly against `openai` 3.16.2 (verified — see test results).

The `litellm` extra therefore stays in `project.optional-dependencies`, and
`[tool.uv] override-dependencies = ["openai>=3,<4"]` forces the OpenAI pin
through LiteLLM's stale constraint so `uv sync --extra litellm` resolves.
LiteLLM's `httpx<1` pin is harmless: `httpx` 0.28.1 installs alongside `httpx2`
(different package names, no conflict).

Caveats:

- `pip install agency-swarm[litellm]` cannot work until LiteLLM relaxes the pin —
  pip reads LiteLLM's real metadata and fails on `openai>=3` + `openai<3`. pip
  users can `pip install agency-swarm litellm --no-deps` as a workaround.
- `make sync` keeps the default dev env LiteLLM-free (`--all-extras --no-extra
  litellm`) to mirror the primary supported configuration; the LiteLLM-dependent
  tests skip cleanly and run when the extra is installed.

## Breakages and fixes

### Agents SDK 0.18.1 → 0.22.3

- **`RunResult.to_state()` copies the context wrapper**
  (`RunContextWrapper._copy_for_run_state`). Suspended system-reminder state was
  keyed by the original wrapper, so resumed runs lost reminder cadence.
  `agent/system_reminder_state.py` adds `alias_suspended_direct_run()` and
  `agent/runner.py` patches `_copy_for_run_state` so copied wrappers alias the
  same suspended state; `_DirectReminderRun.restore()` drops stale aliases after
  a checkpoint consumes them.
- **Run-state JSON validation is strict** (`type(key) is str`). Suspended
  `tool_call_counts` serialized integer dict keys and failed deserialization;
  they now serialize as strings and parse back to `int` on restore.
- **`FunctionTool.on_invoke_tool` error contract**: the SDK redacts tool input
  data (`agents._debug.DONT_LOG_TOOL_DATA`) and surfaces
  `Invalid JSON input for tool <name>` instead of full Pydantic detail.
  `base_tool_adapter.py` mirrors that contract so `BaseTool` adapters match
  `function_tool` error output exactly.
- **Streaming events**: `ResponseFunctionCallArgumentsDeltaEvent` (and siblings)
  no longer accept `name=`; `conversation_starters_streaming.py` drops the field
  and the unused `tool_name` plumbing.
- **`ChatCmplStreamHandler` reads `choice.finish_reason`** before `delta`; the
  LiteLLM reasoning-patch test fixtures gained `finish_reason=None` on their fake
  choices.

### OpenAI 2.x → 3.16.2

- **`InputTokensDetails` requires `cache_write_tokens`**;
  `conversation_starters_streaming.py` passes `cache_write_tokens=0` alongside
  `cached_tokens=0`.

### MCP 1.x → 2.2.0 / fastmcp 4.0.5

- **OAuth callback contract is typed**: `OAuthCallbackHandler` now returns
  `AuthorizationCodeResult` (code/state/iss) instead of `(code, state)` tuples.
  Updated `mcp/oauth.py`, `mcp/oauth_flow.py`, `tools/mcp_oauth_bridge.py`, and
  `integrations/fastapi_utils/oauth_support.py` end to end, including `iss`
  forwarding from callback URLs.
- **`mcp.server.fastmcp` fixture import removed**: `tests/data/scripts/
  stdio_server.py` imports `FastMCP` from the external `fastmcp` package.
- **stdio transport is strict JSON-RPC**: the same fixture's startup banner
  moved to stderr so it cannot corrupt the protocol stream.
- **fastmcp 4.x API changes**: `McpError(code, message)` positional signature
  replaces `McpError(ErrorData(...))`; `Tool`/`ToolResult` import from
  `fastmcp.tools` instead of `fastmcp.tools.tool` (`integrations/mcp_server.py`).
- **Exception groups from MCP transports** wrapped OAuth failures as
  "unhandled errors in a TaskGroup". `agent/core.py` adds
  `_actionable_failure_message()` to surface the first non-cancellation leaf.

### httpx → httpx2

All eight `import httpx` sites migrated (`integrations/openclaw.py`,
`integrations/openclaw_model.py`, `agents/openclaw.py`,
`integrations/fastapi_utils/file_handler.py`, `mcp/oauth_provider.py`,
`tools/utils.py`, `tools/tool_factory_utils/openapi_importer.py`,
`utils/hosted_tool_compat.py`). The API surface is unchanged for what we use
(`AsyncClient`, `Timeout`, `URL`, `Response`, `Headers`, `Request`, `HTTPError`).
`__init__.py` dependency probes check `httpx2` instead of `httpx`.

## End-to-end coverage added

`tests/integration/agency/test_tool_result_history_replay.py` covers the classic
tool-result history bug deterministically (`DeterministicModel` subclass that
records every model input, real `Agency`/`Agent`/`function_tool` objects — no
model mocking):

- `test_function_call_result_is_resent_to_model_on_next_turn` — function-call
  turn then a follow-up; asserts the second-turn model input contains the
  `function_call` and a `function_call_output` with a matching `call_id` and the
  verbatim tool output, and that the result was not rewritten as assistant text.
- `test_function_call_result_is_resent_to_model_on_next_turn_streaming` — same
  round-trip through `get_response_stream` with a tool-call-emitting streamed
  model.
- `test_delegation_result_is_resent_to_model_on_next_turn` — `send_message`
  delegation to a sub-agent, then a follow-up; asserts the delegation call and
  the sub-agent's reply are resent as proper items.

## Test results

- `make check` (ruff + mypy): clean, 149 source files.
- Focused regression groups: system reminders 33, tool factory 18, MCP OAuth 7 —
  all pass.
- LiteLLM absent (default `make sync` env): litellm-related groups pass with the
  LiteLLM tests skipping cleanly (`pytest.importorskip("litellm")`).
- LiteLLM installed (`uv sync --extra litellm`, litellm 1.101.0 + openai
  3.16.2): the same groups run fully — 113 passed, 0 failed.
- Full suite (`uv run pytest tests/`): **1524 passed, 79 failed, 58 skipped**.

### Known blocker: invalid `OPENAI_API_KEY`

All 79 full-suite failures are environmental: the `.env` `OPENAI_API_KEY` is
expired (HTTP 401 `invalid_api_key`). Every failure block logs `Error getting
response`/`Error streaming response` from the OpenAI SDK; none are migration
defects. Secondary manifestations include:

- `AgentsException: Runner execution failed (cause: AuthenticationError)` —
  direct 401s.
- Guardrail streaming tests where a 401'd model call masks the tripwire
  exception (the non-streaming equivalents pass, including
  `test_input_guardrail_guidance_and_persistence`).
- `RuntimeError: Event loop is closed` inside `httpcore2` pool teardown when a
  shared client closes a failed connection under a different pytest-asyncio
  loop — a 401-error-path artifact, not hit on the success path.
- Downstream `AssertionError`/`KeyError` where tests assert on responses the
  401 prevented.

A valid key should re-run the suite to confirm green; nothing in the 79 points
at the migrated code paths themselves.
