"""End-to-end integration tests for FastAPI `client_config` behavior."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

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
        self.__class__.requests_seen.append(
            {
                "path": self.path,
                "authorization": auth,
                "x-agency-id": self.headers.get("x-agency-id"),
                "x-sandbox-id": self.headers.get("x-sandbox-id"),
                "x-user-id": self.headers.get("x-user-id"),
            }
        )

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

    # Prove the request hit our stub and used the overridden API key.
    seen = _ChatCompletionsStubHandler.requests_seen
    assert len(seen) == 1
    assert seen[0]["path"] == "/v1/chat/completions"
    assert seen[0]["authorization"] == "Bearer sk-test"


def test_client_config_merges_default_headers_and_allows_overrides(openai_stub_base_url: str) -> None:
    """Request-level default_headers merge with existing client headers (request wins)."""

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        original_client = AsyncOpenAI(
            api_key="sk-test",
            base_url=f"{openai_stub_base_url}/v1",
            default_headers={
                "x-agency-id": "agency-orig",
                "x-sandbox-id": "sandbox-orig",
            },
        )

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
            "client_config": {
                # No base_url/api_key override: use the existing client's values.
                "default_headers": {
                    "x-sandbox-id": "sandbox-override",
                    "x-user-id": "user-123",
                }
            },
        },
    )
    assert res.status_code == 200
    assert res.json()["response"] == "hello from stub"

    seen = _ChatCompletionsStubHandler.requests_seen
    assert len(seen) == 1
    assert seen[0]["authorization"] == "Bearer sk-test"
    assert seen[0]["x-agency-id"] == "agency-orig"
    assert seen[0]["x-sandbox-id"] == "sandbox-override"
    assert seen[0]["x-user-id"] == "user-123"


def test_client_config_is_scoped_to_single_request(openai_stub_base_url: str) -> None:
    """Request-level overrides should not persist across requests."""

    cached_agency = None

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        nonlocal cached_agency
        if cached_agency is None:
            original_client = AsyncOpenAI(
                api_key="sk-original",
                base_url=f"{openai_stub_base_url}/v1",
            )
            agent = Agent(
                name="TestAgent",
                instructions="You are a test agent.",
                model=OpenAIChatCompletionsModel(model="gpt-4o-mini", openai_client=original_client),
            )
            cached_agency = Agency(
                agent,
                load_threads_callback=load_threads_callback,
                save_threads_callback=save_threads_callback,
            )
        return cached_agency

    app = run_fastapi(
        agencies={"test_agency": create_agency},
        return_app=True,
        app_token_env="",  # disable auth for test
        enable_agui=False,
    )
    client = TestClient(app)

    res = client.post(
        "/test_agency/get_response",
        json={"message": "hi", "client_config": {"api_key": "sk-test"}},
    )
    assert res.status_code == 200
    assert res.json()["response"] == "hello from stub"

    res = client.post("/test_agency/get_response", json={"message": "hi again"})
    assert res.status_code == 200
    assert res.json()["response"] == "hello from stub"

    seen = _ChatCompletionsStubHandler.requests_seen
    assert len(seen) == 2
    assert seen[0]["authorization"] == "Bearer sk-test"
    assert seen[1]["authorization"] == "Bearer sk-original"


def test_client_config_passes_request_scoped_upload_client(
    openai_stub_base_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """file_urls uploads should receive request-level OpenAI client overrides."""
    captured: dict[str, object] = {}

    async def _fake_upload_from_urls(_file_urls, allowed_local_dirs=None, openai_client=None):
        del allowed_local_dirs
        assert openai_client is not None
        captured["api_key"] = openai_client.api_key
        captured["base_url"] = str(openai_client.base_url)
        captured["headers"] = dict(openai_client.default_headers or {})
        return {"doc.txt": "file-123"}

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.upload_from_urls",
        _fake_upload_from_urls,
    )

    async def _noop_prepare_and_attach_files(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "agency_swarm.agent.attachment_manager.AttachmentManager.prepare_and_attach_files",
        _noop_prepare_and_attach_files,
    )

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        original_client = AsyncOpenAI(api_key="sk-original", base_url=f"{openai_stub_base_url}/v1")
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
        app_token_env="",
        enable_agui=False,
    )
    client = TestClient(app)

    res = client.post(
        "/test_agency/get_response",
        json={
            "message": "hi",
            "file_urls": {"doc.txt": "https://example.com/doc.txt"},
            "client_config": {
                "base_url": f"{openai_stub_base_url}/v1",
                "api_key": "sk-request",
                "default_headers": {"x-request-id": "req-1"},
            },
        },
    )

    assert res.status_code == 200
    assert res.json()["response"] == "hello from stub"
    assert res.json()["file_ids_map"] == {"doc.txt": "file-123"}
    assert captured["api_key"] == "sk-request"
    assert str(captured["base_url"]).startswith(f"{openai_stub_base_url}/v1")
    assert isinstance(captured["headers"], dict)
    assert captured["headers"]["x-request-id"] == "req-1"


def test_default_headers_only_uses_existing_upload_auth(
    openai_stub_base_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """default_headers-only client_config should preserve baseline upload auth."""
    captured: dict[str, object] = {}

    async def _fake_upload_from_urls(_file_urls, allowed_local_dirs=None, openai_client=None):
        del allowed_local_dirs
        assert openai_client is not None
        captured["api_key"] = openai_client.api_key
        captured["base_url"] = str(openai_client.base_url)
        captured["headers"] = dict(openai_client.default_headers or {})
        return {"doc.txt": "file-123"}

    monkeypatch.setattr(
        "agency_swarm.integrations.fastapi_utils.endpoint_handlers.upload_from_urls",
        _fake_upload_from_urls,
    )

    async def _noop_prepare_and_attach_files(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "agency_swarm.agent.attachment_manager.AttachmentManager.prepare_and_attach_files",
        _noop_prepare_and_attach_files,
    )

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        original_client = AsyncOpenAI(
            api_key="sk-agent",
            base_url=f"{openai_stub_base_url}/v1",
            default_headers={"x-agency-id": "agency-orig"},
        )
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
        app_token_env="",
        enable_agui=False,
    )
    client = TestClient(app)

    res = client.post(
        "/test_agency/get_response",
        json={
            "message": "hi",
            "file_urls": {"doc.txt": "https://example.com/doc.txt"},
            "client_config": {"default_headers": {"x-request-id": "req-1"}},
        },
    )

    assert res.status_code == 200
    assert res.json()["response"] == "hello from stub"
    assert res.json()["file_ids_map"] == {"doc.txt": "file-123"}
    assert captured["api_key"] == "sk-agent"
    assert str(captured["base_url"]).startswith(f"{openai_stub_base_url}/v1")
    assert isinstance(captured["headers"], dict)
    assert captured["headers"]["x-agency-id"] == "agency-orig"
    assert captured["headers"]["x-request-id"] == "req-1"


def test_client_config_does_not_leak_codex_base_url_into_anthropic_litellm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic LiteLLM runs must ignore a forwarded Codex OAuth base_url."""
    pytest.importorskip("agents.extensions.models.litellm_model")
    from agents.extensions.models.litellm_model import LitellmModel

    captured: dict[str, object] = {}

    async def fake_get_response(self, message, **kwargs):
        del message, kwargs
        captured["model"] = self.model
        return SimpleNamespace(final_output="ok")

    monkeypatch.setattr(Agent, "get_response", fake_get_response)

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(
            name="TestAgent",
            instructions="You are a test agent.",
            model="litellm/anthropic/claude-sonnet-4",
        )
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    app = run_fastapi(
        agencies={"test_agency": create_agency},
        return_app=True,
        app_token_env="",
        enable_agui=False,
    )
    client = TestClient(app)

    res = client.post(
        "/test_agency/get_response",
        json={
            "message": "hi",
            "client_config": {
                "base_url": "https://chatgpt.com/backend-api/codex",
                "api_key": "sk-openai-gateway",
                "litellm_keys": {"anthropic": "sk-ant"},
            },
        },
    )

    assert res.status_code == 200
    assert res.json()["response"] == "ok"

    model = captured["model"]
    assert isinstance(model, LitellmModel)
    assert model.model == "anthropic/claude-sonnet-4"
    assert model.base_url is None
    assert model.api_key == "sk-ant"


def test_client_config_litellm_keys_dropped_when_litellm_unavailable(
    openai_stub_base_url: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Forwarding `litellm_keys` to a bridge without litellm should warn-and-drop, not 422."""
    from agency_swarm.integrations.fastapi_utils import request_models

    monkeypatch.setattr(request_models, "_LITELLM_INSTALLED", False)

    def create_agency(load_threads_callback=None, save_threads_callback=None):
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
        app_token_env="",
        enable_agui=False,
    )
    client = TestClient(app)

    with caplog.at_level("WARNING", logger=request_models.__name__):
        res = client.post(
            "/test_agency/get_response",
            json={
                "message": "hi",
                "client_config": {
                    "base_url": f"{openai_stub_base_url}/v1",
                    "api_key": "sk-test",
                    "litellm_keys": {"anthropic": "sk-ant-xxx"},
                },
            },
        )

    assert res.status_code == 200
    assert res.json()["response"] == "hello from stub"
    assert any("litellm is not installed" in record.message for record in caplog.records)

    seen = _ChatCompletionsStubHandler.requests_seen
    assert len(seen) == 1
    assert seen[0]["authorization"] == "Bearer sk-test"
