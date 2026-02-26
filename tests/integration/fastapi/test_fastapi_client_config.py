"""End-to-end integration tests for FastAPI `client_config` behavior."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient
from openai import AsyncOpenAI

from agency_swarm import Agency, Agent, run_fastapi

pytest.importorskip("agents")
from agents import OpenAIChatCompletionsModel


class _ChatCompletionsStubHandler(BaseHTTPRequestHandler):
    """A tiny local stub for OpenAI Chat Completions API."""

    # Shared state set by the fixture.
    expected_api_key: str = ""
    requests_seen: list[dict] = []

    def log_message(self, *_args, **_kwargs):  # noqa: D401, N802
        """Silence default HTTP server logging in test output."""

    def do_POST(self):  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        auth = self.headers.get("authorization") or self.headers.get("Authorization")
        self.__class__.requests_seen.append({"path": self.path, "authorization": auth})

        if auth != f"Bearer {self.__class__.expected_api_key}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return

        # Minimal Chat Completions response shape.
        response = {
            "id": "chatcmpl_test_1",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-4o-mini",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "hello from stub"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

        payload = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def openai_stub_base_url() -> str:
    """Start a local HTTP server that mimics OpenAI's /v1/chat/completions endpoint."""
    handler = _ChatCompletionsStubHandler
    handler.expected_api_key = "sk-test"
    handler.requests_seen = []

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_client_config_overrides_openai_client_base_url_and_key(openai_stub_base_url: str) -> None:
    """FastAPI request `client_config` routes the model call to the provided base_url."""

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        # The request's client_config should override this client during the request.
        original_client = AsyncOpenAI(api_key="sk-original", base_url="http://example.invalid")

        agent = Agent(
            name="TestAgent",
            instructions="You are a test agent.",
            model=OpenAIChatCompletionsModel(model="gpt-4o-mini", openai_client=original_client),
        )
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(
        agencies={"test_agency": create_agency},
        return_app=True,
        app_token_env="",  # disable auth for test
        enable_agui=False,
    )
    client = TestClient(app)

    res = client.post(
        "/test_agency/get_response",
        json={
            "message": "hi",
            # The OpenAI SDK joins "<base_url> + /chat/completions", so use a v1 base URL.
            "client_config": {"base_url": f"{openai_stub_base_url}/v1", "api_key": "sk-test"},
        },
    )
    assert res.status_code == 200
    assert res.json()["response"] == "hello from stub"
    snapshot_messages = [
        message
        for message in res.json().get("new_messages", [])
        if isinstance(message, dict)
        and message.get("message_origin") == "provider_raw_response_snapshot"
        and isinstance(message.get("raw_response"), dict)
    ]
    assert snapshot_messages
    assert "output" in snapshot_messages[0]["raw_response"]

    # Prove the request hit our stub and used the overridden API key.
    seen = _ChatCompletionsStubHandler.requests_seen
    assert len(seen) == 1
    assert seen[0]["path"] == "/v1/chat/completions"
    assert seen[0]["authorization"] == "Bearer sk-test"
