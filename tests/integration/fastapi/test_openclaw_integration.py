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
        provider_model="openai/gpt-4o-mini",
        gateway_command="openclaw gateway",
    )


def test_openclaw_proxy_mount_paths_exist(tmp_path: Path) -> None:
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
                headers={"content-type": "application/json"},
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
                {"type": "web_search"},
            ],
            "tool_choice": {"type": "function", "name": "calc"},
            "metadata": {"attempt": 1, "scope": {"a": 1}, "label": "ok"},
            "include": ["response.output_text"],
            "parallel_tool_calls": True,
        },
    )

    assert response.status_code == 200
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
    assert forwarded["model"] == "openai/gpt-4o-mini"
    assert forwarded["input"] == [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hello"}]}
    ]
    assert forwarded["tools"] == [{"type": "function", "function": {"name": "calc", "parameters": {"type": "object"}}}]
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
        headers = {"content-type": "text/event-stream"}

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
    assert 'data: {"chunk": 1}' in response.text
    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:18789/v1/responses"
    assert captured["json"]["stream"] is True
    assert captured["closed"] is True
    assert captured["context"].exited is True


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


def test_openclaw_ensure_layout_creates_config_parent(tmp_path: Path) -> None:
    config = _build_openclaw_config(tmp_path)
    custom_config_path = tmp_path / "config-root" / "nested" / "openclaw.json"
    runtime = OpenClawRuntime(replace(config, config_path=custom_config_path))

    runtime.ensure_layout()

    assert custom_config_path.exists()
    assert custom_config_path.parent.is_dir()


def test_openclaw_startup_and_shutdown_handlers_are_sync(tmp_path: Path) -> None:
    app = FastAPI()
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))

    startup_handlers = [handler for handler in app.router.on_startup if handler.__name__ == "_startup_openclaw_runtime"]
    shutdown_handlers = [
        handler for handler in app.router.on_shutdown if handler.__name__ == "_shutdown_openclaw_runtime"
    ]

    assert startup_handlers, "startup handler not registered"
    assert shutdown_handlers, "shutdown handler not registered"
    assert not inspect.iscoroutinefunction(startup_handlers[0])
    assert not inspect.iscoroutinefunction(shutdown_handlers[0])


def test_openclaw_proxy_requires_app_token(
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

    unauthorized = client.post(
        "/openclaw/v1/responses",
        json={"model": "openclaw:main", "input": "hello"},
    )
    assert unauthorized.status_code in (401, 403)

    authorized = client.post(
        "/openclaw/v1/responses",
        json={"model": "openclaw:main", "input": "hello"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert authorized.status_code == 200
