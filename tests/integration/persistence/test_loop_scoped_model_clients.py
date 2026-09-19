"""Cross-event-loop coverage for Agency Swarm's model builders.

``build_openclaw_responses_model`` and ``build_openrouter_chat_model`` create
the ``AsyncOpenAI`` stored on ``Agent.model``. Each ``get_response_sync`` call
runs its own ``asyncio.run`` loop, and under httpx2 a pooled keep-alive
connection is bound to the loop that created it — a fixed client crashes the
second call with ``RuntimeError: Event loop is closed``.

These tests drive two sequential ``get_response_sync`` calls per builder
against a local keep-alive stub, the same regression shape as
``test_context_persistence_between_sync_calls``, without needing a live
OpenClaw worker or OpenRouter account.
"""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.integrations.openclaw_model import build_openclaw_responses_model
from agency_swarm.utils.openrouter import build_openrouter_chat_model

_RESPONSES_PAYLOAD = {
    "id": "resp_stub",
    "object": "response",
    "created_at": 1758000000,
    "status": "completed",
    "model": "openclaw-test",
    "output": [
        {
            "type": "message",
            "id": "msg_stub",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "openclaw-ok", "annotations": []}],
        }
    ],
    "parallel_tool_calls": True,
    "tool_choice": "auto",
    "tools": [],
    "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
}

_CHAT_COMPLETION_PAYLOAD = {
    "id": "chatcmpl_stub",
    "object": "chat.completion",
    "created": 1758000000,
    "model": "openai/gpt-5",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "openrouter-ok"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
}


class _StubOpenAIHandler(BaseHTTPRequestHandler):
    """Serves canned OpenAI Responses/Chat Completions payloads over keep-alive HTTP/1.1."""

    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = _CHAT_COMPLETION_PAYLOAD if self.path.endswith("/chat/completions") else _RESPONSES_PAYLOAD
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def stub_openai_base_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubOpenAIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_openclaw_model_two_sequential_get_response_sync(stub_openai_base_url: str):
    """A stored OpenClaw model must not carry dead event-loop state between sync calls."""
    model = build_openclaw_responses_model(base_url=f"{stub_openai_base_url}/v1", api_key="test-key")
    agency = Agency(Agent(name="Stub", instructions="Reply briefly.", model=model))

    first = agency.get_response_sync("hello")
    second = agency.get_response_sync("hello again")

    assert first.final_output == "openclaw-ok"
    assert second.final_output == "openclaw-ok"


def test_openrouter_model_two_sequential_get_response_sync(stub_openai_base_url: str):
    """A stored OpenRouter model must not carry dead event-loop state between sync calls."""
    model = build_openrouter_chat_model("openrouter/openai/gpt-5", api_key="test-key", base_url=stub_openai_base_url)
    agency = Agency(Agent(name="Stub", instructions="Reply briefly.", model=model))

    first = agency.get_response_sync("hello")
    second = agency.get_response_sync("hello again")

    assert first.final_output == "openrouter-ok"
    assert second.final_output == "openrouter-ok"
