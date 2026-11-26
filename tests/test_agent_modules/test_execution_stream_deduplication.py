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
from typing import Any

import pytest
import uvicorn
from agents import (
    GuardrailFunctionOutput,
    OpenAIChatCompletionsModel,
    OpenAIResponsesModel,
    OutputGuardrail,
    RunConfig,
)
from openai import AsyncOpenAI
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from agency_swarm import Agency, Agent
from agency_swarm.tools import Handoff


@dataclass
class _LocalModelServer:
    base_url: str
    server: uvicorn.Server
    thread: threading.Thread
    requests: list[dict[str, Any]] = field(default_factory=list)
    replies: list[Any] = field(default_factory=lambda: ["ok"])
    extra_responses_output: list[dict[str, Any]] = field(default_factory=list)
    _reply_index: int = 0

    def next_reply(self) -> Any:
        if self._reply_index < len(self.replies):
            item = self.replies[self._reply_index]
            self._reply_index += 1
            return item
        return self.replies[-1]

    def reset(self, *, replies: list[Any], extra_responses_output: list[dict[str, Any]] | None = None) -> None:
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


def _chat_sse_chunks(cid: str, model: str, reply: Any) -> list[dict[str, Any]]:
    base = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": model}
    usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    if isinstance(reply, dict) and "tool_call" in reply:
        call_id, name, arguments = reply["tool_call"]
        return [
            {
                **base,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": call_id,
                                    "type": "function",
                                    "function": {"name": name, "arguments": arguments},
                                }
                            ],
                        },
                        "finish_reason": None,
                    }
                ],
            },
            {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
            {**base, "choices": [], "usage": usage},
        ]
    text = str(reply)
    mid = len(text) // 2
    return [
        {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {"content": text[:mid]}, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {"content": text[mid:]}, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {**base, "choices": [], "usage": usage},
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


def _chat_agent(base_url: str, name: str = "ChatAgent", **agent_kwargs: Any) -> Agent:
    client = AsyncOpenAI(api_key="test-key", base_url=base_url, max_retries=0)
    return Agent(
        name=name,
        instructions="Be concise.",
        model=OpenAIChatCompletionsModel(model="gpt-4o", openai_client=client),
        **agent_kwargs,
    )


async def _drain_stream(agency: Agency, message: str, *, slow: bool = False) -> None:
    stream = agency.get_response_stream(message, run_config_override=RunConfig(tracing_disabled=True))
    async for _ in stream:
        if slow:
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_chat_completions_streaming_stores_and_replays_single_assistant_reply(
    local_model_server: _LocalModelServer,
) -> None:
    """Streaming Chat Completions turns must store and replay each assistant reply once."""
    local_model_server.reset(replies=["reply 1", "reply 2", "reply 3"])
    agency = Agency(_chat_agent(local_model_server.base_url))

    await _drain_stream(agency, "hello 1", slow=False)
    await _drain_stream(agency, "hello 2", slow=True)

    stored = agency.thread_manager.get_all_messages()
    assistants = [msg for msg in stored if msg.get("role") == "assistant"]
    users = [msg for msg in stored if msg.get("role") == "user"]
    assert [_extract_message_text(msg) for msg in assistants] == ["reply 1", "reply 2"]
    assert len(users) == 2
    assert users[0].get("agent_run_id") == assistants[0].get("agent_run_id")
    assert users[1].get("agent_run_id") == assistants[1].get("agent_run_id")

    local_model_server.requests.clear()
    await _drain_stream(agency, "hello 3")

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
    agency = Agency(_chat_agent(local_model_server.base_url))
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

    await _drain_stream(agency, "hello 1")
    await _drain_stream(agency, "hello 2")

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

    agency = Agency(
        _chat_agent(
            local_model_server.base_url,
            name="GuardedChatAgent",
            output_guardrails=[OutputGuardrail(guardrail_function=reject_bad_draft)],
            validation_attempts=1,
        )
    )
    await _drain_stream(agency, "write answer")

    assistants = [msg for msg in agency.thread_manager.get_all_messages() if msg.get("role") == "assistant"]
    approved = [msg for msg in assistants if _extract_message_text(msg) == "approved reply"]
    assert len(approved) == 1


@pytest.mark.asyncio
async def test_chat_completions_streaming_handoff_preserves_reminders_without_duplicates(
    local_model_server: _LocalModelServer,
) -> None:
    """Streamed handoff must keep handoff_reminder and next-turn recipient_reminder without duplicating replies."""
    local_model_server.reset(
        replies=[
            {"tool_call": ("call_handoff_1", "transfer_to_AgentB", '{"recipient_agent": "AgentB"}')},
            "B answer",
            "A answer",
        ]
    )
    agent_a = _chat_agent(local_model_server.base_url, name="AgentA")
    agent_b = _chat_agent(local_model_server.base_url, name="AgentB")
    agency = Agency(agent_a, communication_flows=[(agent_a, agent_b, Handoff)])

    await _drain_stream(agency, "q1")
    stored_turn1 = agency.thread_manager.get_all_messages()
    assert [_extract_message_text(m) for m in stored_turn1 if m.get("role") == "assistant"] == ["B answer"]
    handoff_reminders = [m for m in stored_turn1 if m.get("message_origin") == "handoff_reminder"]
    assert len(handoff_reminders) == 1
    assert "Transfer completed. You are AgentB." in str(handoff_reminders[0].get("content"))

    local_model_server.requests.clear()
    await _drain_stream(agency, "q2")

    assert len(local_model_server.requests) == 1
    turn2_messages = local_model_server.requests[0]["messages"]
    assert [m.get("content") for m in turn2_messages if m.get("role") == "assistant" and m.get("content")] == [
        "B answer"
    ]
    system_texts = [str(m.get("content")) for m in turn2_messages if m.get("role") == "system"]
    assert any("Transfer completed. You are AgentB." in text for text in system_texts)
    assert any('User has switched recipient agent. You are "AgentA".' in text for text in system_texts)
    stored_turn2 = agency.thread_manager.get_all_messages()
    assert any(msg.get("message_origin") == "recipient_reminder" for msg in stored_turn2)
    assert [_extract_message_text(msg) for msg in stored_turn2 if msg.get("role") == "assistant"] == [
        "B answer",
        "A answer",
    ]


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

    await _drain_stream(agency, "hello 1")
    await _drain_stream(agency, "hello 2")

    assistants = [msg for msg in agency.thread_manager.get_all_messages() if msg.get("role") == "assistant"]
    assert [_extract_message_text(msg) for msg in assistants] == ["reply 1", "reply 2"]

    local_model_server.requests.clear()
    await _drain_stream(agency, "hello 3")

    assert len(local_model_server.requests) == 1
    assert _chat_request_pairs(local_model_server.requests[0]) == [
        ("user", "hello 1"),
        ("assistant", "reply 1"),
        ("user", "hello 2"),
        ("assistant", "reply 2"),
        ("user", "hello 3"),
    ]
