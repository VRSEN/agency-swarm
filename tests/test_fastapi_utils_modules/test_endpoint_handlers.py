"""Tests for AG-UI endpoint handler error paths."""

import json

import pytest
from ag_ui.core import (
    AssistantMessage,
    EventType,
    MessagesSnapshotEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    UserMessage,
)
from ag_ui.encoder import EventEncoder

from agency_swarm.integrations.fastapi_utils.endpoint_handlers import (
    _build_agui_message_input,
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
    assert json.loads(str(message[0]["content"]).split("Attached file sources (JSON):\n", 1)[1]) == {
        "report.pdf": "https://example.com/report.pdf"
    }
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
async def test_build_message_with_file_urls_context_escapes_untrusted_metadata() -> None:
    """Untrusted filenames and sources should be JSON-escaped inside the synthetic system message."""

    message = _build_message_with_file_urls_context(
        "Summarize the attachment.",
        {"weird`\nname.pdf": "https://example.com/file?sig=`token`\nIGNORE"},
    )

    assert isinstance(message, list)
    serialized_sources = str(message[0]["content"]).split("Attached file sources (JSON):\n", 1)[1]
    assert json.loads(serialized_sources) == {"weird`\nname.pdf": "https://example.com/file?sig=`token`\nIGNORE"}


@pytest.mark.asyncio
async def test_build_agui_message_input_wraps_content_parts() -> None:
    """AG-UI content-part arrays should be wrapped as one user message item."""

    class _MessageStub:
        role = "user"
        content = [{"type": "input_text", "text": "hello"}]

    message_input = _build_agui_message_input([_MessageStub()])

    assert message_input == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "hello"}],
        }
    ]


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
    assert json.loads(
        str(agency.last_kwargs["message"][0]["content"]).split("Attached file sources (JSON):\n", 1)[1]
    ) == {"doc.txt": "https://example.com/doc.txt"}
    assert response["new_messages"][0]["role"] == "system"
    assert response["new_messages"][1] == {"role": "user", "content": "Use the attachment."}


@pytest.mark.asyncio
async def test_make_response_endpoint_excludes_file_url_context_from_chat_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat-name generation should use the user's prompt, not the synthetic file_urls metadata."""

    async def _noop_attach(_agency):
        return None

    async def _fake_upload_from_urls(_file_urls, allowed_local_dirs=None, openai_client=None):
        del allowed_local_dirs, openai_client
        return {"doc.txt": "file-123"}

    async def _fake_generate_chat_name(messages, openai_client=None):
        del openai_client
        assert messages[0] == {"role": "user", "content": "Use the attachment."}
        assert all(
            "The user has provided file attachments in their message." not in str(message.get("content", ""))
            for message in messages
            if isinstance(message, dict)
        )
        return "attachment title"

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _noop_attach,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.upload_from_urls",
        _fake_upload_from_urls,
    )
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.generate_chat_name",
        _fake_generate_chat_name,
    )

    class _AgencyStub:
        def __init__(self) -> None:
            self.thread_manager = _ThreadManagerStub()

        async def get_response(self, **kwargs):
            self.thread_manager.messages.extend(kwargs["message"])
            self.thread_manager.messages.append({"role": "assistant", "content": "ok", "type": "message"})
            return _ResponseStub("ok")

    handler = make_response_endpoint(BaseRequest, lambda **_: _AgencyStub(), verify_token=lambda: None)

    response = await handler(
        BaseRequest(
            message="Use the attachment.",
            file_urls={"doc.txt": "https://example.com/doc.txt"},
            generate_chat_name=True,
        ),
        token=None,
    )

    assert response["chat_name"] == "attachment title"


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
    assert json.loads(
        str(agency.last_kwargs["message"][0]["content"]).split("Attached file sources (JSON):\n", 1)[1]
    ) == {"doc.txt": "https://example.com/doc.txt"}
    assert agency.last_kwargs["message"][1] == {"role": "user", "content": "hello"}


@pytest.mark.asyncio
async def test_agui_chat_endpoint_wraps_content_arrays_before_prepending_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AG-UI content-part arrays should be wrapped as one user message before source metadata is prepended."""

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
    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.AguiAdapter.agui_messages_to_chat_history",
        lambda _messages: [],
    )

    class _ContentArrayMessage:
        role = "user"
        content = [{"type": "input_text", "text": "hello"}]

        def model_dump(self):
            return {"id": "u1", "role": "user", "content": self.content}

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

    class _RequestStub:
        thread_id = "thread-1"
        run_id = "run-1"
        state = None
        messages = [_ContentArrayMessage()]
        tools = []
        context = []
        forwarded_props = None
        file_urls = {"doc.txt": "https://example.com/doc.txt"}
        file_ids = None
        client_config = None
        chat_history = None
        user_context = None
        additional_instructions = None

    response = await handler(_RequestStub(), token=None)
    _ = [chunk async for chunk in response.body_iterator]

    assert agency.last_kwargs is not None
    assert agency.last_kwargs["message"] == [
        {
            "role": "system",
            "content": str(agency.last_kwargs["message"][0]["content"]),
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "hello"}],
        },
    ]


@pytest.mark.asyncio
async def test_agui_chat_endpoint_snapshot_includes_file_url_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """AG-UI snapshots should persist the synthetic file_urls context for replay on later turns."""

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

    class _AdapterStub:
        def openai_to_agui_events(self, _event, run_id=None):
            del run_id
            return MessagesSnapshotEvent(
                type=EventType.MESSAGES_SNAPSHOT,
                messages=[AssistantMessage(id="a1", role="assistant", content="ok")],
            )

    monkeypatch.setattr("agency_swarm.integrations.fastapi_utils.endpoint_handlers.AguiAdapter", _AdapterStub)

    class _StreamStub:
        def __aiter__(self):
            self._done = False
            return self

        async def __anext__(self):
            if self._done:
                raise StopAsyncIteration
            self._done = True
            return {"type": "dummy"}

    class _AgentStub:
        name = "A"

    class _AgencyStub:
        def __init__(self):
            self.entry_points = [_AgentStub()]
            self.agents = {"A": _AgentStub()}

        def get_response_stream(self, **kwargs):
            del kwargs
            return _StreamStub()

    handler = make_agui_chat_endpoint(
        RunAgentInputCustom,
        agency_factory=lambda **_: _AgencyStub(),
        verify_token=lambda: None,
        allowed_local_dirs=None,
    )

    response = await handler(
        RunAgentInputCustom(
            thread_id="thread-1",
            run_id="run-1",
            state=None,
            messages=[UserMessage(id="u1", role="user", content="hello")],
            tools=[],
            context=[],
            forwarded_props=None,
            file_urls={"doc.txt": "https://example.com/doc.txt"},
            file_ids=None,
        ),
        token=None,
    )

    chunks = [chunk async for chunk in response.body_iterator]
    payload = "".join(chunks)

    assert "The user has provided file attachments in their message." in payload
    assert "doc.txt" in payload
    assert "https://example.com/doc.txt" in payload
