"""Tests for AG-UI endpoint handler error paths."""

import pytest
from ag_ui.core import EventType, RunErrorEvent, RunFinishedEvent, RunStartedEvent
from ag_ui.encoder import EventEncoder
from fastapi import HTTPException

from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_agui_chat_endpoint, make_response_endpoint
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, RunAgentInputCustom
from agency_swarm.memory import MemoryIdentity


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

    response = await handler(http_request=None, request=request, token=None)

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
async def test_response_endpoint_rejects_client_memory_identity_by_default(monkeypatch) -> None:
    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _AgencyStub:
        def __init__(self):
            self.thread_manager = _ThreadManager()

        async def get_response(self, **_kwargs):
            raise AssertionError("get_response should not run when client memory identity is rejected")

    async def _attach_noop(_agency):
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _attach_noop,
    )

    handler = make_response_endpoint(
        BaseRequest,
        agency_factory=lambda **_: _AgencyStub(),
        verify_token=lambda: None,
    )

    with pytest.raises(HTTPException, match="Client-supplied durable memory identity is disabled by default"):
        await handler(http_request=None, request=BaseRequest(message="hi", user_id="victim-user"), token=None)


@pytest.mark.asyncio
async def test_response_endpoint_uses_server_bound_memory_identity(monkeypatch) -> None:
    captured: dict[str, MemoryIdentity | None] = {"memory_identity": None}

    class _ThreadManager:
        def get_all_messages(self):
            return []

    class _Response:
        def __init__(self, final_output: str):
            self.final_output = final_output

    class _AgencyStub:
        def __init__(self):
            self.thread_manager = _ThreadManager()

        async def get_response(self, **kwargs):
            captured["memory_identity"] = kwargs["memory_identity"]
            return _Response("ok")

    async def _attach_noop(_agency):
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _attach_noop,
    )

    def _resolve_memory_identity(_http_request, _request):
        return MemoryIdentity(user_id="trusted-user", agency_id="agency-1", session_id="chat-1")

    handler = make_response_endpoint(
        BaseRequest,
        agency_factory=lambda **_: _AgencyStub(),
        verify_token=lambda: None,
        memory_identity_resolver=_resolve_memory_identity,
    )

    response = await handler(http_request=None, request=BaseRequest(message="hi", user_id="attacker-user"), token=None)

    assert response["response"] == "ok"
    assert captured["memory_identity"] == MemoryIdentity(
        user_id="trusted-user",
        agency_id="agency-1",
        session_id="chat-1",
    )
