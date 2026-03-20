"""Tests for AG-UI endpoint handler error paths."""

import pytest
from ag_ui.core import EventType, RunErrorEvent, RunFinishedEvent, RunStartedEvent, UserMessage
from ag_ui.encoder import EventEncoder

from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    _build_message_with_file_urls_context,
    make_agui_chat_endpoint,
    make_response_endpoint,
)
from agency_swarm.integrations.fastapi_utils.request_models import BaseRequest, RunAgentInputCustom


class _ThreadManagerStub:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def get_all_messages(self) -> list[dict]:
        return list(self.messages)


class _ResponseStub:
    def __init__(self, final_output: str) -> None:
        self.final_output = final_output


@pytest.mark.asyncio
async def test_build_message_with_file_urls_context_prepends_system_message() -> None:
    """file_urls should prepend one system message before the user turn."""

    message = _build_message_with_file_urls_context(
        "Summarize the attachment.",
        {"report.pdf": "https://example.com/report.pdf"},
    )

    assert isinstance(message, list)
    assert message[0]["role"] == "system"
    assert "The user has provided file attachments in their message." in str(message[0]["content"])
    assert "`report.pdf`: `https://example.com/report.pdf`" in str(message[0]["content"])
    assert message[1] == {"role": "user", "content": "Summarize the attachment."}


@pytest.mark.asyncio
async def test_build_message_with_file_urls_context_preserves_structured_input_items() -> None:
    """Structured input lists should stay top-level after prepending the source-context message."""

    message = _build_message_with_file_urls_context(
        [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "Earlier reply"},
            {"role": "user", "content": "Latest message"},
        ],
        {"report.pdf": "https://example.com/report.pdf"},
    )

    assert isinstance(message, list)
    assert message[0]["role"] == "system"
    assert message[1] == {"role": "user", "content": "First message"}
    assert message[2] == {"role": "assistant", "content": "Earlier reply"}
    assert message[3] == {"role": "user", "content": "Latest message"}


@pytest.mark.asyncio
async def test_make_response_endpoint_persists_file_url_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-streaming requests should persist file_urls source context via a system message."""

    async def _noop_attach(_agency):
        return None

    async def _fake_upload_from_urls(_file_urls, allowed_local_dirs=None, openai_client=None):
        del allowed_local_dirs, openai_client
        return {"doc.txt": "file-123"}

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _noop_attach,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.upload_from_urls",
        _fake_upload_from_urls,
    )

    class _AgencyStub:
        def __init__(self) -> None:
            self.thread_manager = _ThreadManagerStub()
            self.last_kwargs = None

        async def get_response(self, **kwargs):
            self.last_kwargs = kwargs
            message = kwargs["message"]
            assert isinstance(message, list)
            self.thread_manager.messages.extend(message)
            self.thread_manager.messages.append({"role": "assistant", "content": "ok", "type": "message"})
            return _ResponseStub("ok")

    agency = _AgencyStub()
    handler = make_response_endpoint(BaseRequest, lambda **_: agency, verify_token=lambda: None)

    response = await handler(
        BaseRequest(
            message="Use the attachment.",
            file_urls={"doc.txt": "https://example.com/doc.txt"},
        ),
        token=None,
    )

    assert response["response"] == "ok"
    assert response["file_ids_map"] == {"doc.txt": "file-123"}
    assert agency.last_kwargs is not None
    assert agency.last_kwargs["file_ids"] == ["file-123"]
    assert isinstance(agency.last_kwargs["message"], list)
    assert agency.last_kwargs["message"][0]["role"] == "system"
    assert "`doc.txt`: `https://example.com/doc.txt`" in str(agency.last_kwargs["message"][0]["content"])
    assert response["new_messages"][0]["role"] == "system"
    assert response["new_messages"][1] == {"role": "user", "content": "Use the attachment."}


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
async def test_agui_chat_endpoint_prepends_file_url_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """AG-UI requests should prepend the persisted source-context system message."""

    async def _noop_attach(_agency):
        return None

    async def _fake_upload_from_urls(_file_urls, allowed_local_dirs=None, openai_client=None):
        del allowed_local_dirs, openai_client
        return {"doc.txt": "file-123"}

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _noop_attach,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.upload_from_urls",
        _fake_upload_from_urls,
    )

    class _StreamStub:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _AgentStub:
        name = "A"

    class _AgencyStub:
        def __init__(self):
            self.entry_points = [_AgentStub()]
            self.agents = {"A": _AgentStub()}
            self.last_kwargs = None

        def get_response_stream(self, **kwargs):
            self.last_kwargs = kwargs
            return _StreamStub()

    agency = _AgencyStub()
    handler = make_agui_chat_endpoint(
        RunAgentInputCustom,
        agency_factory=lambda **_: agency,
        verify_token=lambda: None,
        allowed_local_dirs=None,
    )

    request = RunAgentInputCustom(
        thread_id="thread-1",
        run_id="run-1",
        state=None,
        messages=[UserMessage(id="u1", role="user", content="hello")],
        tools=[],
        context=[],
        forwarded_props=None,
        file_urls={"doc.txt": "https://example.com/doc.txt"},
        file_ids=None,
    )

    response = await handler(request, token=None)
    _ = [chunk async for chunk in response.body_iterator]

    assert agency.last_kwargs is not None
    assert agency.last_kwargs["file_ids"] == ["file-123"]
    assert isinstance(agency.last_kwargs["message"], list)
    assert agency.last_kwargs["message"][0]["role"] == "system"
    assert "`doc.txt`: `https://example.com/doc.txt`" in str(agency.last_kwargs["message"][0]["content"])
    assert agency.last_kwargs["message"][1] == {"role": "user", "content": "hello"}
