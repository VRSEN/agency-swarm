"""Transport lifetime regressions without model or network calls."""

import asyncio
import json
from collections.abc import AsyncGenerator

import pytest
from starlette.applications import Starlette
from starlette.requests import ClientDisconnect, Request
from starlette.responses import StreamingResponse
from starlette.types import Message

from agency_swarm import Agency, Agent
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, ClientConfig, RunAgentInputCustom
from agency_swarm.integrations.fastapi_utils.request_state import _AgencyRequestLease, _get_agency_request_states
from agency_swarm.integrations.fastapi_utils.run_registry import ActiveRunRegistry


def _request() -> Request:
    async def receive() -> Message:
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    return Request({"type": "http", "headers": [], "app": Starlette()}, receive=receive)


@pytest.fixture
def agency(monkeypatch: pytest.MonkeyPatch) -> Agency:
    async def attach(_agency: Agency) -> None:
        return None

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", attach)
    return Agency(Agent(name="Lifecycle", instructions="Never called", model="gpt-4o-mini"))


def _install_stream(monkeypatch: pytest.MonkeyPatch, stream: StreamingRunResponse) -> None:
    monkeypatch.setattr(Agency, "get_response_stream", lambda _self, **_kwargs: stream)


async def _empty() -> AsyncGenerator[dict]:
    if False:
        yield {}


async def _open(agency: Agency, registry: ActiveRunRegistry) -> tuple[StreamingResponse, str]:
    handler = endpoint_handlers.make_stream_endpoint(BaseRequest, lambda **_: agency, lambda: None, registry)
    response = await handler(http_request=_request(), request=BaseRequest(message="hello"), token=None)
    meta = await anext(response.body_iterator)
    run_id = json.loads(meta.split("data: ", 1)[1])["run_id"]
    return response, run_id


async def test_close_at_meta_releases_registry_and_lease(agency: Agency, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_stream(monkeypatch, StreamingRunResponse(_empty()))
    registry = ActiveRunRegistry()
    response, run_id = await _open(agency, registry)
    active = await registry.get(run_id)

    await response.body_iterator.aclose()

    assert await registry.get(run_id) is None
    assert active.done_event.is_set()
    assert all(state.active_regular_requests == 0 for state in await _get_agency_request_states(agency))


async def test_close_after_event_closes_underlying_iterator(agency: Agency, monkeypatch: pytest.MonkeyPatch) -> None:
    closed = asyncio.Event()

    async def source() -> AsyncGenerator[dict]:
        try:
            yield {"type": "test"}
            await asyncio.Event().wait()
        finally:
            closed.set()

    _install_stream(monkeypatch, StreamingRunResponse(source()))
    response, _ = await _open(agency, ActiveRunRegistry())
    await anext(response.body_iterator)

    await response.body_iterator.aclose()

    assert closed.is_set()


async def test_after_turn_does_not_cancel_pending_event(agency: Agency, monkeypatch: pytest.MonkeyPatch) -> None:
    started = asyncio.Event()
    finish_turn = asyncio.Event()
    interrupted = asyncio.Event()

    async def source() -> AsyncGenerator[dict]:
        started.set()
        try:
            await finish_turn.wait()
            yield {"type": "turn_finished"}
        except asyncio.CancelledError:
            interrupted.set()
            raise

    _install_stream(monkeypatch, StreamingRunResponse(source()))
    registry = ActiveRunRegistry()
    response, run_id = await _open(agency, registry)
    consumer = asyncio.create_task(anext(response.body_iterator))
    await started.wait()
    active = await registry.mark_cancelled(run_id, "after_turn")
    active.stream.cancel("after_turn")
    # Flush callbacks using a scheduled marker, without a timing-based sleep.
    flushed = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_later(0, flushed.set_result, None)
    await flushed
    finish_turn.set()
    first = await consumer
    rest = [chunk async for chunk in response.body_iterator]

    assert not interrupted.is_set()
    assert '"turn_finished"' in first
    assert any('"cancelled": true' in chunk for chunk in rest)


async def test_cancelled_setup_restores_client_override(agency: Agency, monkeypatch: pytest.MonkeyPatch) -> None:
    entered = asyncio.Event()

    async def upload(*_args: object, **_kwargs: object) -> dict[str, str]:
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(endpoint_handlers, "upload_from_urls", upload)
    agent = next(iter(agency.agents.values()))
    original_model = agent.model
    handler = endpoint_handlers.make_stream_endpoint(BaseRequest, lambda **_: agency, lambda: None, ActiveRunRegistry())
    setup = asyncio.create_task(
        handler(
            http_request=_request(),
            request=BaseRequest(
                message="hello",
                file_urls={"file.txt": "https://example.com/file.txt"},
                client_config=ClientConfig(api_key="test-key", base_url="https://example.com/v1"),
            ),
            token=None,
        )
    )
    done, _ = await asyncio.wait(
        {setup, asyncio.create_task(entered.wait())}, timeout=2, return_when=asyncio.FIRST_COMPLETED
    )
    if setup in done:
        await setup
    assert entered.is_set()
    setup.cancel()
    with pytest.raises(asyncio.CancelledError):
        await setup

    assert agent.model == original_model
    assert all(not state.override_active for state in await _get_agency_request_states(agency))


async def test_registry_completion_follows_request_cleanup(agency: Agency, monkeypatch: pytest.MonkeyPatch) -> None:
    cleanup_entered = asyncio.Event()
    allow_cleanup = asyncio.Event()
    original = endpoint_handlers._release_agency_request_lease

    async def release(lease: _AgencyRequestLease) -> None:
        cleanup_entered.set()
        await allow_cleanup.wait()
        await original(lease)

    monkeypatch.setattr(endpoint_handlers, "_release_agency_request_lease", release)
    _install_stream(monkeypatch, StreamingRunResponse(_empty()))
    registry = ActiveRunRegistry()
    response, run_id = await _open(agency, registry)
    active = await registry.get(run_id)

    async def consume() -> list[str]:
        return [chunk async for chunk in response.body_iterator]

    consumer = asyncio.create_task(consume())
    await cleanup_entered.wait()
    completed_early = active.done_event.is_set()
    allow_cleanup.set()
    await consumer

    assert not completed_early
    assert active.done_event.is_set()


def _agui_request() -> RunAgentInputCustom:
    return RunAgentInputCustom(
        thread_id="thread-lifecycle",
        run_id="run-lifecycle",
        state={},
        tools=[],
        context=[],
        forwarded_props={},
        messages=[{"id": "message-lifecycle", "role": "user", "content": "hello"}],
    )


async def _open_agui(agency: Agency) -> StreamingResponse:
    handler = endpoint_handlers.make_agui_chat_endpoint(RunAgentInputCustom, lambda **_: agency, lambda: None)
    return await handler(request=_agui_request(), token=None)


async def test_agui_close_at_started_frame_releases_lease(agency: Agency) -> None:
    response = await _open_agui(agency)
    assert "RUN_STARTED" in await anext(response.body_iterator)

    await response.body_iterator.aclose()

    assert all(state.active_regular_requests == 0 for state in await _get_agency_request_states(agency))


async def test_agui_close_at_adapted_frame_closes_source(agency: Agency, monkeypatch: pytest.MonkeyPatch) -> None:
    from ag_ui.core import EventType, TextMessageStartEvent

    closed = asyncio.Event()

    async def source() -> AsyncGenerator[dict]:
        try:
            yield {"type": "test"}
            await asyncio.Event().wait()
        finally:
            closed.set()

    monkeypatch.setattr(
        endpoint_handlers.AguiAdapter,
        "openai_to_agui_events",
        lambda *_args, **_kwargs: TextMessageStartEvent(
            type=EventType.TEXT_MESSAGE_START, message_id="message", role="assistant"
        ),
    )
    _install_stream(monkeypatch, StreamingRunResponse(source()))
    response = await _open_agui(agency)
    await anext(response.body_iterator)
    assert "TEXT_MESSAGE_START" in await anext(response.body_iterator)

    await response.body_iterator.aclose()

    assert closed.is_set()


@pytest.mark.parametrize("endpoint", ["sse", "agui"])
@pytest.mark.parametrize("fail_after", [0, 1, 2])
async def test_response_send_failure_releases_request(
    agency: Agency, monkeypatch: pytest.MonkeyPatch, endpoint: str, fail_after: int
) -> None:
    _install_stream(monkeypatch, StreamingRunResponse(_empty()))
    registry = ActiveRunRegistry()
    if endpoint == "sse":
        handler = endpoint_handlers.make_stream_endpoint(BaseRequest, lambda **_: agency, lambda: None, registry)
        response = await handler(http_request=_request(), request=BaseRequest(message="hello"), token=None)
    else:
        response = await _open_agui(agency)
    sent = 0

    async def send(_message: Message) -> None:
        nonlocal sent
        if sent == fail_after:
            raise OSError("transport closed")
        sent += 1

    async def receive() -> Message:
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    with pytest.raises(ClientDisconnect):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)

    assert all(state.active_regular_requests == 0 for state in await _get_agency_request_states(agency))
    assert registry._runs == {}


async def test_final_messages_are_snapshotted_before_releasing_lease(
    agency: Agency, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = endpoint_handlers._release_agency_request_lease

    async def source() -> AsyncGenerator[dict]:
        agency.thread_manager.add_message({"role": "assistant", "content": "this run"})
        yield {"type": "done"}

    async def release(lease: _AgencyRequestLease) -> None:
        await original(lease)
        # A subsequent request may use the shared message store immediately.
        agency.thread_manager.add_message({"role": "assistant", "content": "next run"})

    monkeypatch.setattr(endpoint_handlers, "_release_agency_request_lease", release)
    _install_stream(monkeypatch, StreamingRunResponse(source()))
    response, _ = await _open(agency, ActiveRunRegistry())
    chunks = [chunk async for chunk in response.body_iterator]
    final = next(chunk for chunk in chunks if chunk.startswith("event: messages"))

    assert "this run" in final
    assert "next run" not in final


async def test_response_cancellation_clears_oauth_context_after_cleanup_cancel(
    agency: Agency, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agency_swarm.mcp.oauth import (
        OAuthRuntimeContext,
        get_oauth_runtime_context,
        set_oauth_runtime_context,
    )

    running = asyncio.Event()
    cleaning = asyncio.Event()
    release = asyncio.Event()
    original = endpoint_handlers._release_agency_request_lease

    async def get_response(_self: Agency, **_kwargs: object) -> None:
        set_oauth_runtime_context(OAuthRuntimeContext(mode="saas_stream", user_id="request-user"))
        running.set()
        await asyncio.Event().wait()

    async def release_lease(lease: _AgencyRequestLease) -> None:
        cleaning.set()
        await release.wait()
        await original(lease)

    monkeypatch.setattr(Agency, "get_response", get_response)
    monkeypatch.setattr(endpoint_handlers, "_release_agency_request_lease", release_lease)
    handler = endpoint_handlers.make_response_endpoint(BaseRequest, lambda **_: agency, lambda: None)

    async def call() -> OAuthRuntimeContext | None:
        try:
            await handler(request=BaseRequest(message="hello"), token=None)
        except asyncio.CancelledError:
            return get_oauth_runtime_context()
        raise AssertionError("Expected cancellation")

    task = asyncio.create_task(call())
    await running.wait()
    task.cancel()
    await cleaning.wait()
    task.cancel()
    release.set()

    assert await task is None


@pytest.mark.parametrize("endpoint", ["sse", "agui"])
async def test_asgi_disconnect_closes_blocked_stream(
    agency: Agency, monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    started = asyncio.Event()
    closed = asyncio.Event()

    async def source() -> AsyncGenerator[dict]:
        try:
            started.set()
            await asyncio.Event().wait()
            yield {"type": "unreachable"}
        finally:
            closed.set()

    _install_stream(monkeypatch, StreamingRunResponse(source()))
    registry = ActiveRunRegistry()
    if endpoint == "sse":
        handler = endpoint_handlers.make_stream_endpoint(BaseRequest, lambda **_: agency, lambda: None, registry)
        response = await handler(http_request=_request(), request=BaseRequest(message="hello"), token=None)
    else:
        response = await _open_agui(agency)

    async def receive() -> Message:
        await started.wait()
        return {"type": "http.disconnect"}

    async def send(_message: Message) -> None:
        return None

    await asyncio.wait_for(response({"type": "http", "asgi": {"spec_version": "2.0"}}, receive, send), timeout=2)

    assert closed.is_set()
    assert registry._runs == {}
    assert all(state.active_regular_requests == 0 for state in await _get_agency_request_states(agency))
