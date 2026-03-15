"""Tests for AG-UI endpoint handler error paths."""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from ag_ui.core import EventType, RunErrorEvent, RunFinishedEvent, RunStartedEvent
from ag_ui.encoder import EventEncoder

import agency_swarm.integrations.fastapi_utils.endpoint_handlers as endpoint_handlers_module
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_agui_chat_endpoint, make_stream_endpoint
from agency_swarm.integrations.fastapi_utils.oauth_support import FastAPIOAuthConfig, OAuthStateRegistry
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, RunAgentInputCustom


@pytest.mark.asyncio
async def test_agui_file_urls_error_emits_lifecycle_events(tmp_path):
    """file_urls failures should emit run started/error/finished events to avoid client hangs."""

    encoder = EventEncoder()

    class _AgentStub:
        name = "A"

    class _AgencyStub:
        def __init__(self):
            self.entry_points = [_AgentStub()]
            self.agents = {"A": _AgentStub()}

    # Build handler with no allowlist so local file triggers a PermissionError.
    handler = make_agui_chat_endpoint(
        RunAgentInputCustom,
        agency_factory=lambda **_: _AgencyStub(),
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
            self.thread_manager = type("_ThreadManager", (), {"get_all_messages": lambda self: []})()

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


@pytest.mark.asyncio
async def test_stream_endpoint_cancels_oauth_attach_task_on_stream_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closing the SSE stream must cancel the background OAuth attach task."""

    cancelled = asyncio.Event()
    redirect_emitted = asyncio.Event()

    async def _oauth_wait_attach(_agency: Any) -> None:
        from agency_swarm.mcp.oauth import get_oauth_runtime_context

        runtime_context = get_oauth_runtime_context()
        assert runtime_context is not None
        assert runtime_context.redirect_handler_factory is not None
        redirect_handler = runtime_context.redirect_handler_factory("demo-server")
        await redirect_handler("https://idp.example.com/authorize?state=stream-close")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def _empty_stream() -> AsyncGenerator[dict[str, Any]]:
        if False:
            yield {}

    class _StubAgency:
        def __init__(self) -> None:
            self.agents = {}
            self.entry_points = []
            self.thread_manager = type("_ThreadManager", (), {"get_all_messages": lambda self: []})()

        def get_response_stream(self, **_kwargs: Any) -> StreamingRunResponse:
            return StreamingRunResponse(_empty_stream())

    class _Request:
        async def is_disconnected(self) -> bool:
            return False

    monkeypatch.setattr(endpoint_handlers_module, "attach_persistent_mcp_servers", _oauth_wait_attach)

    handler = make_stream_endpoint(
        BaseRequest,
        agency_factory=lambda **_: _StubAgency(),
        verify_token=lambda: None,
        run_registry=endpoint_handlers_module.ActiveRunRegistry(),
        oauth_config=FastAPIOAuthConfig(OAuthStateRegistry()),
    )

    response = await handler(
        http_request=_Request(),
        request=BaseRequest(message="hi"),
        token=None,
        user_id="u1",
    )
    chunks: list[str] = []

    async def _consume_stream() -> None:
        async for chunk in response.body_iterator:
            chunks.append(chunk)
            if "event: oauth_redirect" in chunk:
                redirect_emitted.set()

    consumer = asyncio.create_task(_consume_stream())
    await asyncio.wait_for(redirect_emitted.wait(), timeout=0.2)
    consumer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await consumer

    await asyncio.wait_for(cancelled.wait(), timeout=0.2)
