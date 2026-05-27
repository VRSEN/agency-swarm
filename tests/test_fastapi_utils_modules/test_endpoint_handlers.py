"""Tests for AG-UI endpoint handler error paths."""

from types import SimpleNamespace

import pytest
from ag_ui.core import EventType, RunErrorEvent, RunFinishedEvent, RunStartedEvent, UserMessage
from ag_ui.encoder import EventEncoder

from agency_swarm.integrations.fastapi_utils.endpoint_handlers import make_agui_chat_endpoint
from agency_swarm.integrations.fastapi_utils.request_models import RunAgentInputCustom


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
async def test_agui_endpoint_keeps_suppressed_provider_message_in_snapshot_state(monkeypatch):
    """Suppressed provider message snapshots should still update later AG-UI snapshots."""

    async def _noop_attach(_agency):
        return None

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.attach_persistent_mcp_servers",
        _noop_attach,
    )

    provider_data = {"model": "gemini/gemini-2.5-flash", "response_id": "response_1"}
    streamed_message = SimpleNamespace(id="msg-1", type="message", provider_data=provider_data, content=[])
    final_message = SimpleNamespace(
        id="msg-1",
        type="message",
        provider_data=provider_data,
        content=[SimpleNamespace(text="Answer", annotations=[])],
    )
    tool_item = SimpleNamespace(raw_item={"call_id": "call-1"}, call_id="call-1", output="Tool result")

    class _AgentStub:
        name = "A"

    class _AgencyStub:
        def __init__(self):
            self.entry_points = [_AgentStub()]
            self.agents = {"A": _AgentStub()}
            self.mcp_servers = []

        def get_response_stream(self, **_kwargs):
            async def _stream():
                yield SimpleNamespace(
                    type="raw_response_event",
                    data=SimpleNamespace(type="response.output_item.added", item=streamed_message, output_index=0),
                )
                yield SimpleNamespace(
                    type="raw_response_event",
                    data=SimpleNamespace(type="response.output_text.delta", item_id="msg-1", delta="Answer"),
                )
                yield SimpleNamespace(
                    type="run_item_stream_event",
                    name="message_output_created",
                    item=SimpleNamespace(raw_item=final_message),
                )
                yield SimpleNamespace(type="run_item_stream_event", name="tool_output", item=tool_item)

            return _stream()

    handler = make_agui_chat_endpoint(
        RunAgentInputCustom,
        agency_factory=lambda **_: _AgencyStub(),
        verify_token=lambda: None,
    )
    request = RunAgentInputCustom(
        thread_id="thread-1",
        run_id="run-1",
        state=None,
        messages=[UserMessage(id="u1", role="user", content="Hi")],
        tools=[],
        context=[],
        forwarded_props=None,
        file_urls=None,
        file_ids=None,
    )

    response = await handler(request, token=None)
    chunks = [chunk async for chunk in response.body_iterator]
    snapshots = [chunk for chunk in chunks if '"type":"MESSAGES_SNAPSHOT"' in chunk]

    assert len(snapshots) == 1
    assert '"content":"Answer"' in snapshots[0]
    assert '"content":"Tool result"' in snapshots[0]
