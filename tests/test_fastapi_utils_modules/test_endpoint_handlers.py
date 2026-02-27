"""Tests for AG-UI endpoint handler error paths."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from ag_ui.core import EventType, RunErrorEvent, RunFinishedEvent, RunStartedEvent
from ag_ui.encoder import EventEncoder

import agency_swarm.integrations.fastapi_utils.endpoint_handlers as endpoint_handlers_module
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_agui_chat_endpoint
from agency_swarm.integrations.fastapi_utils.oauth_support import FastAPIOAuthConfig, OAuthStateRegistry
from agency_swarm.integrations.fastapi_utils.request_models import RunAgentInputCustom


@pytest.mark.asyncio
async def test_agui_file_urls_error_emits_lifecycle_events(tmp_path):
    """file_urls failures should emit run started/error/finished events to avoid client hangs."""

    encoder = EventEncoder()

    # Build handler with no allowlist so local file triggers a PermissionError.
    handler = make_agui_chat_endpoint(
        RunAgentInputCustom,
        agency_factory=lambda **_: None,  # not reached on error path
        verify_token=lambda: None,
        allowed_local_dirs=None,
    )

    file_path = tmp_path / "local.txt"
    file_path.write_text("hello", encoding="utf-8")

    request = RunAgentInputCustom(
        thread_id="thread-1",
        run_id="run-1",
        state=None,
        messages=[],
        tools=[],
        context=[],
        forwarded_props=None,
        file_urls={"local.txt": str(file_path)},
        file_ids=None,
    )

    response = await handler(request, token=None)

    chunks = [chunk async for chunk in response.body_iterator]

    expected_events = [
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id="thread-1", run_id="run-1"),
        RunErrorEvent(
            type=EventType.RUN_ERROR,
            message="Error downloading file from provided urls: Local file access is disabled for this server.",
        ),
        RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id="thread-1", run_id="run-1"),
    ]
    expected_chunks = [encoder.encode(event) for event in expected_events]

    assert chunks == expected_chunks
    assert response.media_type == encoder.get_content_type()


@pytest.mark.asyncio
async def test_agui_stream_emits_keepalive_comments_while_oauth_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    """AG-UI stream should mirror OAuth keepalive behavior."""

    async def _oauth_wait_attach(_agency: Any) -> None:
        from agency_swarm.mcp.oauth import get_oauth_runtime_context

        runtime_context = get_oauth_runtime_context()
        assert runtime_context is not None
        assert runtime_context.redirect_handler_factory is not None
        redirect_handler = runtime_context.redirect_handler_factory("demo-server")
        await redirect_handler("https://idp.example.com/authorize?state=agui-keepalive")
        await asyncio.sleep(0.03)

    async def _empty_stream() -> AsyncGenerator[dict[str, Any]]:
        if False:
            yield {}

    class _StubAgency:
        def __init__(self) -> None:
            self.agents = {}
            self.entry_points = []

        def get_response_stream(self, **_kwargs: Any) -> StreamingRunResponse:
            return StreamingRunResponse(_empty_stream())

    monkeypatch.setattr(endpoint_handlers_module, "attach_persistent_mcp_servers", _oauth_wait_attach)
    monkeypatch.setattr(endpoint_handlers_module, "OAUTH_KEEPALIVE_SECONDS", 0.01)

    handler = make_agui_chat_endpoint(
        RunAgentInputCustom,
        agency_factory=lambda **_: _StubAgency(),
        verify_token=lambda: None,
        oauth_config=FastAPIOAuthConfig(OAuthStateRegistry()),
    )

    request = RunAgentInputCustom(
        thread_id="thread-1",
        run_id="run-1",
        state=None,
        messages=[],
        tools=[],
        context=[],
        forwarded_props=None,
        chat_history=[{"role": "user", "content": "hi"}],
    )
    response = await handler(request, token=None, user_id="u1")
    chunks = [chunk async for chunk in response.body_iterator]

    assert any(chunk.startswith(": keepalive ") for chunk in chunks)
    assert any("event: oauth_redirect" in chunk for chunk in chunks)
