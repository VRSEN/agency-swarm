from __future__ import annotations

import inspect
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

pytest.importorskip("fastapi.testclient")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agency_swarm import run_fastapi
from agency_swarm.integrations.openclaw import (
    OpenClawIntegrationConfig,
    OpenClawRuntime,
    attach_openclaw_to_fastapi,
    build_openclaw_responses_model,
    normalize_openclaw_responses_request,
)


def _build_openclaw_config(tmp_path: Path) -> OpenClawIntegrationConfig:
    home_dir = tmp_path / "openclaw"
    return OpenClawIntegrationConfig(
        autostart=False,
        host="127.0.0.1",
        port=18789,
        gateway_token="gateway-token",
        home_dir=home_dir,
        state_dir=home_dir / "state",
        config_path=home_dir / "openclaw.json",
        log_path=home_dir / "logs" / "openclaw-gateway.log",
        startup_timeout_seconds=5.0,
        proxy_timeout_seconds=30.0,
        default_model="openclaw:main",
        provider_model="openai/gpt-5-mini",
        gateway_command="openclaw gateway",
    )


def test_openclaw_proxy_mount_paths_exist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("agency_swarm.integrations.openclaw._is_upstream_port_open", lambda _config: True)

    app = FastAPI()
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))
    client = TestClient(app)

    health = client.get("/openclaw/health")
    assert health.status_code == 200
    assert health.json()["upstream_base_url"] == "http://127.0.0.1:18789"

    responses = client.post("/openclaw/v1/responses", json={})
    assert responses.status_code == 400

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/openclaw/v1/responses" in paths
    assert "/openclaw/health" in paths


def test_openclaw_health_reports_unhealthy_when_upstream_is_down(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("agency_swarm.integrations.openclaw._is_upstream_port_open", lambda _config: False)

    app = FastAPI()
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))
    client = TestClient(app)

    health = client.get("/openclaw/health")

    assert health.status_code == 503
    assert health.json() == {"ok": False, "upstream_base_url": "http://127.0.0.1:18789"}


def test_openclaw_proxy_filters_request_keys_and_normalizes_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> httpx.Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return httpx.Response(
                status_code=200,
                content=b'{"ok": true}',
                headers={"content-type": "application/json", "retry-after": "3", "x-request-id": "req-non-stream"},
            )

    monkeypatch.setattr("agency_swarm.integrations.openclaw.httpx.AsyncClient", _FakeAsyncClient)

    app = FastAPI()
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/openclaw/v1/responses",
        json={
            "model": "openclaw:main",
            "input": [{"role": "user", "content": [{"text": "hello"}]}],
            "stream": False,
            "tools": [
                {"type": "function", "function": {"name": "calc", "parameters": {"type": "object"}}},
                {
                    "type": "function",
                    "name": "summarize",
                    "description": "Summarize text",
                    "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
                    "strict": True,
                },
                {"type": "web_search"},
            ],
            "tool_choice": {"type": "function", "name": "calc"},
            "metadata": {"attempt": 1, "scope": {"a": 1}, "label": "ok"},
            "include": ["response.output_text"],
            "parallel_tool_calls": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["retry-after"] == "3"
    assert response.headers["x-request-id"] == "req-non-stream"
    forwarded = captured["json"]
    assert set(forwarded.keys()) <= {
        "model",
        "input",
        "instructions",
        "tools",
        "tool_choice",
        "stream",
        "max_output_tokens",
        "max_tool_calls",
        "user",
        "temperature",
        "top_p",
        "metadata",
        "store",
        "previous_response_id",
        "reasoning",
        "truncation",
    }
    assert "include" not in forwarded
    assert "parallel_tool_calls" not in forwarded
    assert forwarded["model"] == "openai/gpt-5-mini"
    assert forwarded["input"] == [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hello"}]}
    ]
    assert forwarded["tools"] == [
        {"type": "function", "function": {"name": "calc", "parameters": {"type": "object"}}},
        {
            "type": "function",
            "function": {
                "name": "summarize",
                "description": "Summarize text",
                "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
                "strict": True,
            },
        },
    ]
    assert forwarded["tool_choice"] == {"type": "function", "function": {"name": "calc"}}
    assert forwarded["metadata"] == {"attempt": "1", "scope": '{"a": 1}', "label": "ok"}
    assert captured["headers"]["Authorization"] == "Bearer gateway-token"
    assert captured["url"] == "http://127.0.0.1:18789/v1/responses"


def test_openclaw_proxy_stream_passthrough(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeStreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream", "x-request-id": "req-stream"}

        async def aiter_raw(self):
            yield b"event: data\n"
            yield b'data: {"chunk": 1}\n\n'

    class _FakeStreamContext:
        def __init__(self) -> None:
            self._response = _FakeStreamResponse()
            self.exited = False

        async def __aenter__(self) -> _FakeStreamResponse:
            return self._response

        async def __aexit__(self, exc_type, exc, tb) -> None:
            self.exited = True

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._context = _FakeStreamContext()

        def stream(self, method: str, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _FakeStreamContext:
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["context"] = self._context
            return self._context

        async def aclose(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr("agency_swarm.integrations.openclaw.httpx.AsyncClient", _FakeAsyncClient)

    app = FastAPI()
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/openclaw/v1/responses",
        json={"model": "openclaw:main", "input": "hello", "stream": True},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert response.headers["x-request-id"] == "req-stream"
    assert 'data: {"chunk": 1}' in response.text
    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:18789/v1/responses"
    assert captured["json"]["stream"] is True
    assert captured["closed"] is True
    assert captured["context"].exited is True


def test_openclaw_stream_error_path_preserves_upstream_payload_when_stream_context_exit_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {"closed": False}

    class _FailingStreamResponse:
        status_code = 500
        headers = {"content-type": "application/json", "retry-after": "5"}

        async def aread(self) -> bytes:
            return b'{"error":"upstream"}'

    class _FailingStreamContext:
        async def __aenter__(self) -> _FailingStreamResponse:
            return _FailingStreamResponse()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            raise RuntimeError("exit failed")

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def stream(
            self, method: str, url: str, *, headers: dict[str, str], json: dict[str, Any]
        ) -> _FailingStreamContext:
            return _FailingStreamContext()

        async def aclose(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr("agency_swarm.integrations.openclaw.httpx.AsyncClient", _FakeAsyncClient)

    app = FastAPI()
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/openclaw/v1/responses",
        json={"model": "openclaw:main", "input": "hello", "stream": True},
    )

    assert response.status_code == 500
    assert response.text == '{"error":"upstream"}'
    assert response.headers["retry-after"] == "5"
    assert captured["closed"] is True


def test_cancel_endpoint_behavior_remains_on_existing_agency_route(
    agency_factory,
    tmp_path: Path,
) -> None:
    app = run_fastapi(agencies={"test_agency": agency_factory}, return_app=True, app_token_env="")
    assert app is not None
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))
    client = TestClient(app)

    cancel = client.post("/test_agency/cancel_response_stream", json={"run_id": "missing-run"})
    assert cancel.status_code == 404
    assert "not found" in cancel.json()["detail"].lower()

    proxy_cancel = client.post("/openclaw/cancel_response_stream", json={"run_id": "missing-run"})
    assert proxy_cancel.status_code == 404


def test_openclaw_proxy_uses_app_token_auth_when_attached_to_run_fastapi(
    monkeypatch: pytest.MonkeyPatch,
    agency_factory,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APP_TOKEN", "secret-token")

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> httpx.Response:
            return httpx.Response(
                status_code=200,
                content=b'{"ok": true}',
                headers={"content-type": "application/json"},
            )

    monkeypatch.setattr("agency_swarm.integrations.openclaw.httpx.AsyncClient", _FakeAsyncClient)

    app = run_fastapi(agencies={"secure": agency_factory}, return_app=True, app_token_env="APP_TOKEN")
    assert app is not None
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))
    client = TestClient(app)

    unauthorized = client.post("/openclaw/v1/responses", json={"model": "openclaw:main", "input": "hello"})
    assert unauthorized.status_code in (401, 403)

    authorized = client.post(
        "/openclaw/v1/responses",
        json={"model": "openclaw:main", "input": "hello"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert authorized.status_code == 200


def test_openclaw_ensure_layout_creates_config_parent_dir(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    custom_config_path = tmp_path / "external" / "nested" / "openclaw.json"
    runtime = OpenClawRuntime(replace(config, config_path=custom_config_path))

    runtime.ensure_layout()

    assert custom_config_path.exists()
    assert custom_config_path.parent.is_dir()


def test_openclaw_startup_shutdown_handlers_are_sync_functions(tmp_path: Path) -> None:
    app = FastAPI()
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))

    startup_handlers = [handler for handler in app.router.on_startup if handler.__name__ == "_startup_openclaw_runtime"]
    shutdown_handlers = [
        handler for handler in app.router.on_shutdown if handler.__name__ == "_shutdown_openclaw_runtime"
    ]

    assert startup_handlers
    assert shutdown_handlers
    assert not inspect.iscoroutinefunction(startup_handlers[0])
    assert not inspect.iscoroutinefunction(shutdown_handlers[0])


def test_openclaw_gateway_command_port_detection_supports_equals_syntax(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(replace(config, gateway_command="openclaw gateway --port=19000"))

    command = runtime._resolve_gateway_command()
    port_args = [arg for arg in command if arg == "--port" or arg.startswith("--port=")]
    assert port_args == ["--port=19000"]


def test_openclaw_config_from_env_prefers_gateway_command_port(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENCLAW_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("OPENCLAW_PORT", "18789")
    monkeypatch.setenv("OPENCLAW_GATEWAY_COMMAND", "openclaw gateway --port=19000")

    config = OpenClawIntegrationConfig.from_env()

    assert config.port == 19000
    assert config.upstream_base_url == "http://127.0.0.1:19000"


def test_openclaw_start_fails_when_port_is_already_in_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(config)

    monkeypatch.setattr(runtime, "_is_port_open", lambda: True)

    with pytest.raises(RuntimeError, match="already in use"):
        runtime.start()


def test_openclaw_metadata_validation_rejects_non_json_serializable_values() -> None:
    with pytest.raises(ValueError, match="metadata\\['bad'\\] must be JSON-serializable"):
        normalize_openclaw_responses_request(
            {
                "model": "openclaw:main",
                "input": "hello",
                "metadata": {"bad": {1, 2}},
            }
        )


def test_build_openclaw_responses_model_uses_app_token_when_proxy_key_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCLAW_PROXY_API_KEY", raising=False)
    monkeypatch.setenv("APP_TOKEN", "app-token")

    model = build_openclaw_responses_model()

    assert model._client.api_key == "app-token"


def test_build_openclaw_responses_model_prefers_openclaw_proxy_key_over_app_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCLAW_PROXY_API_KEY", "proxy-token")
    monkeypatch.setenv("APP_TOKEN", "app-token")

    model = build_openclaw_responses_model()

    assert model._client.api_key == "proxy-token"


def test_openclaw_start_closes_log_handle_when_popen_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(config)
    opened: dict[str, Any] = {}
    original_open = Path.open

    def _tracked_open(path: Path, *args: Any, **kwargs: Any):
        handle = original_open(path, *args, **kwargs)
        if path == runtime.config.log_path:
            opened["handle"] = handle
        return handle

    def _raise_popen(*args: Any, **kwargs: Any):
        raise OSError("spawn failed")

    monkeypatch.setattr(runtime, "_is_port_open", lambda: False)
    monkeypatch.setattr("pathlib.Path.open", _tracked_open)
    monkeypatch.setattr("agency_swarm.integrations.openclaw.subprocess.Popen", _raise_popen)

    with pytest.raises(OSError, match="spawn failed"):
        runtime.start()

    assert runtime._process is None
    assert runtime._log_handle is None
    assert opened["handle"].closed is True


def test_openclaw_failed_startup_cleans_process_and_log_handle(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _build_openclaw_config(tmp_path)
    runtime = OpenClawRuntime(replace(config, startup_timeout_seconds=0.01))
    runtime.config.log_path.parent.mkdir(parents=True, exist_ok=True)

    class _FakeProcess:
        def __init__(self) -> None:
            self.pid = 4242
            self.killed = False

        def poll(self) -> int | None:
            return None if not self.killed else -9

        def terminate(self) -> None:
            self.killed = True

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout: float | None = None) -> int:
            self.killed = True
            return 0

    fake_process = _FakeProcess()

    monkeypatch.setattr(runtime, "ensure_layout", lambda: None)
    monkeypatch.setattr(runtime, "_resolve_gateway_command", lambda: ["openclaw", "gateway"])
    monkeypatch.setattr(runtime, "_merge_provider_keys_from_dotenv", lambda env: None)
    monkeypatch.setattr(runtime, "_is_port_open", lambda: False)
    monkeypatch.setattr("agency_swarm.integrations.openclaw.subprocess.Popen", lambda *a, **k: fake_process)
    monkeypatch.setattr("agency_swarm.integrations.openclaw.os.killpg", lambda pid, sig: fake_process.terminate())
    monkeypatch.setattr("agency_swarm.integrations.openclaw.time.sleep", lambda _delay: None)

    with pytest.raises(TimeoutError):
        runtime.start()

    assert fake_process.killed is True
    assert runtime._process is None
    assert runtime._log_handle is None
