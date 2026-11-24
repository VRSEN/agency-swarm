"""Offline regression tests for streaming assistant reply deduplication."""

from __future__ import annotations

import asyncio
import json
import socket
import threading
import time
import uuid
from collections.abc import Generator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
import uvicorn
from agents import (
    Agent as SDKAgent,
    GuardrailFunctionOutput,
    OpenAIChatCompletionsModel,
    OpenAIResponsesModel,
    OutputGuardrail,
    RunConfig,
)
from agents.items import MessageOutputItem
from agents.stream_events import AgentUpdatedStreamEvent
from openai import AsyncOpenAI
from openai.types.responses import ResponseOutputMessage, ResponseOutputText
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from agency_swarm import Agency, Agent
from agency_swarm.agent.core import AgencyContext
from agency_swarm.agent.execution_stream_persistence import (
    StreamMetadataStore,
    _persist_streamed_items,
    _update_names_from_event,
)
from agency_swarm.context import MasterContext
from agency_swarm.messages import MessageFormatter
from agency_swarm.utils.thread import ThreadManager


@dataclass
class _LocalModelServer:
    base_url: str
    server: uvicorn.Server
    thread: threading.Thread
    requests: list[dict[str, Any]] = field(default_factory=list)
    replies: list[str] = field(default_factory=lambda: ["ok"])
    extra_responses_output: list[dict[str, Any]] = field(default_factory=list)
    _reply_index: int = 0

    def next_reply(self) -> str:
        if self._reply_index < len(self.replies):
            text = self.replies[self._reply_index]
            self._reply_index += 1
            return text
        return self.replies[-1]

    def reset(self, *, replies: list[str], extra_responses_output: list[dict[str, Any]] | None = None) -> None:
        self.requests.clear()
        self.replies = list(replies)
        self._reply_index = 0
        self.extra_responses_output = list(extra_responses_output or [])


def _build_responses_payload(text: str, model: str, extra_output: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": f"resp_{uuid.uuid4().hex[:12]}",
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": model,
        "output": [
            *extra_output,
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:12]}",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            },
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": 1,
            "output_tokens": 1,
            "total_tokens": 2,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        },
    }


def _sse_event(event_type: str, seq: int, **payload: Any) -> str:
    return f"event: {event_type}\ndata: {json.dumps({'type': event_type, 'sequence_number': seq, **payload})}\n\n"


def _responses_sse_events(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    in_progress = {**payload, "status": "in_progress", "output": []}
    events: list[tuple[str, dict[str, Any]]] = [("response.created", {"response": in_progress})]
    for idx, extra_item in enumerate(payload["output"][:-1]):
        events.append(("response.output_item.added", {"output_index": idx, "item": extra_item}))
        events.append(("response.output_item.done", {"output_index": idx, "item": extra_item}))
    msg_idx = len(payload["output"]) - 1
    item = payload["output"][-1]
    part = item["content"][0]
    base = {"output_index": msg_idx, "item_id": item["id"], "content_index": 0}
    events.extend(
        [
            (
                "response.output_item.added",
                {"output_index": msg_idx, "item": {**item, "status": "in_progress", "content": []}},
            ),
            ("response.content_part.added", {**base, "part": {"type": "output_text", "text": "", "annotations": []}}),
            ("response.output_text.delta", {**base, "delta": part["text"], "logprobs": []}),
            ("response.output_text.done", {**base, "text": part["text"], "logprobs": []}),
            ("response.content_part.done", {**base, "part": part}),
            ("response.output_item.done", {"output_index": msg_idx, "item": item}),
            ("response.completed", {"response": payload}),
        ]
    )
    return events


def _chat_sse_chunks(cid: str, model: str, text: str) -> list[dict[str, Any]]:
    base = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
    mid = len(text) // 2
    return [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {"content": text[:mid]}, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {"content": text[mid:]}, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {**base, "choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
    ]


@pytest.fixture
def local_model_server() -> Generator[_LocalModelServer]:
    """Start a local OpenAI-compatible HTTP server for offline streaming tests."""
    holder: list[_LocalModelServer] = []

    async def handle_responses(request: Request) -> Response:
        state = holder[0]
        body = await request.json()
        state.requests.append(body)
        extra = list(state.extra_responses_output)
        state.extra_responses_output.clear()
        payload = _build_responses_payload(state.next_reply(), body.get("model", "gpt-4o"), extra)
        if not body.get("stream"):
            return JSONResponse(payload)

        async def generate() -> Any:
            for seq, (event_type, event_payload) in enumerate(_responses_sse_events(payload), start=1):
                yield _sse_event(event_type, seq, **event_payload)

        return StreamingResponse(generate(), media_type="text/event-stream")

    async def handle_chat(request: Request) -> Response:
        state = holder[0]
        body = await request.json()
        state.requests.append(body)
        model, text = body.get("model", "gpt-4o"), state.next_reply()
        cid = f"chatcmpl-{uuid.uuid4().hex[:10]}"
        if not body.get("stream"):
            return JSONResponse(
                {
                    "id": cid,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            )

        async def generate() -> Any:
            for chunk in _chat_sse_chunks(cid, model, text):
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    app = Starlette(
        routes=[
            Route("/v1/responses", handle_responses, methods=["POST"]),
            Route("/v1/chat/completions", handle_chat, methods=["POST"]),
        ]
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    state = _LocalModelServer(base_url=f"http://127.0.0.1:{port}/v1", server=server, thread=thread)
    holder.append(state)
    thread.start()
    while not server.started:
        time.sleep(0.02)
    try:
        yield state
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and isinstance(content[0], dict):
        return str(content[0].get("text", ""))
    return str(content)


def _chat_request_pairs(request_body: dict[str, Any]) -> list[tuple[str, Any]]:
    return [
        (msg["role"], msg.get("content")) for msg in request_body.get("messages", []) if msg.get("role") != "system"
    ]


@pytest.mark.asyncio
async def test_chat_completions_streaming_stores_and_replays_single_assistant_reply(
    local_model_server: _LocalModelServer,
) -> None:
    """Streaming Chat Completions turns must store and replay each assistant reply once."""
    local_model_server.reset(replies=["reply 1", "reply 2", "reply 3"])
    client = AsyncOpenAI(api_key="test-key", base_url=local_model_server.base_url, max_retries=0)
    agent = Agent(
        name="ChatAgent",
        instructions="Be concise.",
        model=OpenAIChatCompletionsModel(model="gpt-4o", openai_client=client),
    )
    agency = Agency(agent)
    run_config = RunConfig(tracing_disabled=True)

    for turn, slow in ((1, False), (2, True)):
        stream = agency.get_response_stream(f"hello {turn}", run_config_override=run_config)
        async for _ in stream:
            if slow:
                await asyncio.sleep(0.01)

    stored = agency.thread_manager.get_all_messages()
    assistants = [msg for msg in stored if msg.get("role") == "assistant"]
    users = [msg for msg in stored if msg.get("role") == "user"]
    assert [_extract_message_text(msg) for msg in assistants] == ["reply 1", "reply 2"]
    assert len(users) == 2
    assert users[0].get("agent_run_id") == assistants[0].get("agent_run_id")
    assert users[1].get("agent_run_id") == assistants[1].get("agent_run_id")

    local_model_server.requests.clear()
    stream = agency.get_response_stream("hello 3", run_config_override=run_config)
    async for _ in stream:
        pass

    assert len(local_model_server.requests) == 1
    assert _chat_request_pairs(local_model_server.requests[0]) == [
        ("user", "hello 1"),
        ("assistant", "reply 1"),
        ("user", "hello 2"),
        ("assistant", "reply 2"),
        ("user", "hello 3"),
    ]


@pytest.mark.asyncio
async def test_chat_completions_non_streaming_stores_single_assistant_reply(
    local_model_server: _LocalModelServer,
) -> None:
    """Non-streaming Chat Completions control continues storing one reply per turn."""
    local_model_server.reset(replies=["reply 1", "reply 2"])
    client = AsyncOpenAI(api_key="test-key", base_url=local_model_server.base_url, max_retries=0)
    agent = Agent(
        name="ChatAgent",
        instructions="Be concise.",
        model=OpenAIChatCompletionsModel(model="gpt-4o", openai_client=client),
    )
    agency = Agency(agent)
    run_config = RunConfig(tracing_disabled=True)

    await agency.get_response("hello 1", run_config=run_config)
    await agency.get_response("hello 2", run_config=run_config)

    assistants = [msg for msg in agency.thread_manager.get_all_messages() if msg.get("role") == "assistant"]
    assert [_extract_message_text(msg) for msg in assistants] == ["reply 1", "reply 2"]


@pytest.mark.asyncio
async def test_responses_streaming_preserves_single_copy_and_compaction_item(
    local_model_server: _LocalModelServer,
) -> None:
    """Responses API streaming preserves server-side compaction items and single-copy replies."""
    local_model_server.reset(
        replies=["reply 1", "reply 2"],
        extra_responses_output=[{"type": "compaction", "id": "cmp_123", "encrypted_content": "enc-payload"}],
    )
    client = AsyncOpenAI(api_key="test-key", base_url=local_model_server.base_url, max_retries=0)
    agent = Agent(
        name="ResponsesAgent",
        instructions="Be concise.",
        model=OpenAIResponsesModel(model="gpt-4o", openai_client=client),
    )
    agency = Agency(agent)
    run_config = RunConfig(tracing_disabled=True)

    for turn in (1, 2):
        stream = agency.get_response_stream(f"hello {turn}", run_config_override=run_config)
        async for _ in stream:
            pass

    stored = agency.thread_manager.get_all_messages()
    assert [msg.get("type") for msg in stored] == ["message", "compaction", "message", "message", "message"]
    assistants = [msg for msg in stored if msg.get("role") == "assistant"]
    users = [msg for msg in stored if msg.get("role") == "user"]
    assert [_extract_message_text(msg) for msg in assistants] == ["reply 1", "reply 2"]
    assert users[0].get("agent_run_id") == assistants[0].get("agent_run_id")
    assert users[1].get("agent_run_id") == assistants[1].get("agent_run_id")


@pytest.mark.asyncio
async def test_chat_completions_streaming_output_guardrail_retry_keeps_final_reply_without_duplicates(
    local_model_server: _LocalModelServer,
) -> None:
    """Output-guardrail retry must keep the approved retry reply once without ID collision or duplication."""
    local_model_server.reset(replies=["bad draft", "approved reply"])

    async def reject_bad_draft(_ctx: Any, _agent: Any, output: Any) -> GuardrailFunctionOutput:
        if "bad draft" in str(output):
            return GuardrailFunctionOutput(output_info="Rewrite cleanly.", tripwire_triggered=True)
        return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)

    client = AsyncOpenAI(api_key="test-key", base_url=local_model_server.base_url, max_retries=0)
    agent = Agent(
        name="GuardedChatAgent",
        instructions="Be concise.",
        model=OpenAIChatCompletionsModel(model="gpt-4o", openai_client=client),
        output_guardrails=[OutputGuardrail(guardrail_function=reject_bad_draft)],
        validation_attempts=1,
    )
    agency = Agency(agent)
    run_config = RunConfig(tracing_disabled=True)

    stream = agency.get_response_stream("write answer", run_config_override=run_config)
    async for _ in stream:
        pass

    assistants = [msg for msg in agency.thread_manager.get_all_messages() if msg.get("role") == "assistant"]
    approved = [msg for msg in assistants if _extract_message_text(msg) == "approved reply"]
    assert len(approved) == 1


@pytest.mark.asyncio
async def test_litellm_streaming_stores_and_replays_single_assistant_reply(
    local_model_server: _LocalModelServer,
) -> None:
    """LiteLLM streaming against a local Chat Completions endpoint stores and replays once."""
    litellm_mod = pytest.importorskip("agents.extensions.models.litellm_model", exc_type=ImportError)
    LitellmModel = litellm_mod.LitellmModel

    local_model_server.reset(replies=["reply 1", "reply 2", "reply 3"])
    agent = Agent(
        name="LiteLLMAgent",
        instructions="Be concise.",
        model=LitellmModel(model="openai/gpt-4o", base_url=local_model_server.base_url, api_key="test-key"),
    )
    agency = Agency(agent)
    run_config = RunConfig(tracing_disabled=True)

    for turn in (1, 2):
        stream = agency.get_response_stream(f"hello {turn}", run_config_override=run_config)
        async for _ in stream:
            pass

    assistants = [msg for msg in agency.thread_manager.get_all_messages() if msg.get("role") == "assistant"]
    assert [_extract_message_text(msg) for msg in assistants] == ["reply 1", "reply 2"]

    local_model_server.requests.clear()
    stream = agency.get_response_stream("hello 3", run_config_override=run_config)
    async for _ in stream:
        pass

    assert len(local_model_server.requests) == 1
    assert _chat_request_pairs(local_model_server.requests[0]) == [
        ("user", "hello 1"),
        ("assistant", "reply 1"),
        ("user", "hello 2"),
        ("assistant", "reply 2"),
        ("user", "hello 3"),
    ]


def test_update_names_from_event_preserves_initial_run_id_and_updates_on_switch() -> None:
    """Initial AgentUpdatedStreamEvent keeps the run ID; agent switches or explicit IDs update it."""
    agent_a = SDKAgent(name="AgentA", instructions="a")
    agent_b = SDKAgent(name="AgentB", instructions="b")
    master_context = MasterContext(thread_manager=ThreadManager(), agents={})
    master_context._current_agent_run_id = "agent_run_initial"

    # Initial event for the starting agent must preserve the initial agent_run_id.
    name, run_id = _update_names_from_event(
        AgentUpdatedStreamEvent(new_agent=agent_a),
        "AgentA",
        "agent_run_initial",
        master_context,
    )
    assert (name, run_id) == ("AgentA", "agent_run_initial")
    assert master_context._current_agent_run_id == "agent_run_initial"

    # Switching to another agent mints a new agent_run_id.
    name, switched_run_id = _update_names_from_event(
        AgentUpdatedStreamEvent(new_agent=agent_b),
        name,
        run_id,
        master_context,
    )
    assert name == "AgentB"
    assert switched_run_id != "agent_run_initial"
    assert master_context._current_agent_run_id == switched_run_id

    # A redundant AgentUpdatedStreamEvent for AgentB keeps the active run_id.
    name, same_after_switch = _update_names_from_event(
        AgentUpdatedStreamEvent(new_agent=agent_b),
        name,
        switched_run_id,
        master_context,
    )
    assert (name, same_after_switch) == ("AgentB", switched_run_id)

    # An explicit event.id always overrides agent_run_id.
    explicit_event = SimpleNamespace(type="agent_updated_stream_event", new_agent=agent_b, id="custom_run_id")
    name, explicit_run_id = _update_names_from_event(explicit_event, name, same_after_switch, master_context)
    assert (name, explicit_run_id) == ("AgentB", "custom_run_id")
    assert master_context._current_agent_run_id == "custom_run_id"


def test_persist_streamed_items_replaces_session_written_copy_when_run_id_diverges() -> None:
    """Final persistence replaces session-written copies in mutable_tail even after run-id divergence."""
    thread_manager = ThreadManager()
    user_msg = {
        "type": "message",
        "role": "user",
        "content": "hello",
        "agent": "AgentA",
        "callerAgent": None,
        "agent_run_id": "run_session",
        "history_protocol": MessageFormatter.HISTORY_PROTOCOL_RESPONSES,
    }
    session_copy = {
        "type": "message",
        "id": "msg_run_session_0",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "from B", "annotations": []}],
        "agent": "AgentB",
        "callerAgent": None,
        "agent_run_id": "run_session",
        "history_protocol": MessageFormatter.HISTORY_PROTOCOL_RESPONSES,
    }
    thread_manager.add_messages([user_msg, session_copy])  # type: ignore[list-item]

    agent_a = Agent(name="AgentA", instructions="a")
    agent_b = Agent(name="AgentB", instructions="b")
    final_item = MessageOutputItem(
        agent=agent_b,
        raw_item=ResponseOutputMessage(
            id="msg_run_handoff_0",
            role="assistant",
            status="completed",
            type="message",
            content=[ResponseOutputText(type="output_text", text="from B", annotations=[])],
        ),
    )

    _persist_streamed_items(
        streaming_result=SimpleNamespace(new_items=[final_item]),
        metadata_store=StreamMetadataStore(by_item={id(final_item): ("AgentB", "run_handoff", None, 2)}),
        collected_items=[final_item],
        agent=agent_a,
        sender_name=None,
        parent_run_id=None,
        run_trace_id="trace_1",
        fallback_agent_run_id="run_handoff",
        session_agent_run_id="run_session",
        agency_context=AgencyContext(agency_instance=None, thread_manager=thread_manager),
        initial_saved_count=0,
    )

    stored = thread_manager.get_all_messages()
    assert [msg.get("role") for msg in stored] == ["user", "assistant"]
    assert stored[1].get("id") == "msg_run_handoff_0"
    assert stored[1].get("agent") == "AgentB"
