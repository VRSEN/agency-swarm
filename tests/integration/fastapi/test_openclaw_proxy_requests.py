from __future__ import annotations

import gzip
from pathlib import Path
from typing import Any

import httpx
import pytest

pytest.importorskip("fastapi.testclient")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agency_swarm import run_fastapi
from agency_swarm.integrations import openclaw as openclaw_mod
from agency_swarm.integrations.openclaw import (
    OpenClawIntegrationConfig,
    OpenClawRuntime,
    attach_openclaw_to_fastapi,
    normalize_openclaw_responses_request,
)
from tests.integration.fastapi._openclaw_test_support import _build_openclaw_config


def test_openclaw_config_manual_construction_defaults_to_full_tool_mode(tmp_path: Path) -> None:
    home_dir = tmp_path / "openclaw"
    config = OpenClawIntegrationConfig(
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
        provider_model="openai/gpt-5.4-mini",
        gateway_command="openclaw gateway",
    )

    assert config.tool_mode == "full"


def test_openclaw_health_returns_runtime_snapshot(tmp_path: Path) -> None:
    runtime = OpenClawRuntime(
        OpenClawIntegrationConfig(
            autostart=False,
            host="127.0.0.1",
            port=18789,
            gateway_token="gateway-token",
            home_dir=tmp_path / "openclaw",
            state_dir=tmp_path / "openclaw" / "state",
            config_path=tmp_path / "openclaw" / "openclaw.json",
            log_path=tmp_path / "openclaw" / "logs" / "openclaw-gateway.log",
            startup_timeout_seconds=5.0,
            proxy_timeout_seconds=30.0,
            default_model="openclaw:main",
            provider_model="openai/gpt-5.4-mini",
            gateway_command="openclaw gateway",
        )
    )

    payload = runtime.health()

    assert payload["running"] is False
    assert payload["upstream_base_url"] == "http://127.0.0.1:18789"
    assert payload["home_dir"].endswith("openclaw")
    assert payload["state_dir"].endswith("openclaw/state")


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
                content=gzip.compress(b'{"ok": true}'),
                headers={
                    "content-type": "application/json",
                    "retry-after": "3",
                    "x-request-id": "req-non-stream",
                    "content-encoding": "gzip",
                },
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
    assert response.headers.get("content-encoding") is None
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
    assert forwarded["model"] == "openai/gpt-5.4-mini"
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


def test_openclaw_proxy_preserves_full_history_without_synthesizing_session_fields(
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
            captured["json"] = json
            return httpx.Response(status_code=200, json={"ok": True})

    monkeypatch.setattr("agency_swarm.integrations.openclaw.httpx.AsyncClient", _FakeAsyncClient)

    app = FastAPI()
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/openclaw/v1/responses",
        json={
            "model": "openclaw:main",
            "input": [
                {"role": "user", "content": [{"text": "Hi"}]},
                {"role": "assistant", "content": [{"text": "Hello"}]},
                {"role": "user", "content": [{"text": "Continue with the same chat"}]},
            ],
            "stream": False,
        },
    )

    assert response.status_code == 200
    forwarded = captured["json"]
    assert forwarded["input"] == [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hi"}]},
        {"type": "message", "role": "assistant", "content": [{"type": "input_text", "text": "Hello"}]},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Continue with the same chat"}]},
    ]
    assert "user" not in forwarded
    assert "previous_response_id" not in forwarded


def test_openclaw_proxy_rejects_unsupported_tool_types(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called = {"upstream": False}

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> httpx.Response:
            called["upstream"] = True
            return httpx.Response(status_code=200, json={"ok": True})

    monkeypatch.setattr("agency_swarm.integrations.openclaw.httpx.AsyncClient", _FakeAsyncClient)

    app = FastAPI()
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/openclaw/v1/responses",
        json={
            "model": "openclaw:main",
            "input": "hello",
            "tools": [{"type": "web_search"}],
        },
    )

    assert response.status_code == 400
    assert "not supported by OpenClaw" in response.json()["detail"]
    assert called["upstream"] is False


def test_openclaw_proxy_rejects_non_list_tools(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called = {"upstream": False}

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> httpx.Response:
            called["upstream"] = True
            return httpx.Response(status_code=200, json={"ok": True})

    monkeypatch.setattr("agency_swarm.integrations.openclaw.httpx.AsyncClient", _FakeAsyncClient)

    app = FastAPI()
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))
    client = TestClient(app)

    response = client.post(
        "/openclaw/v1/responses",
        json={
            "model": "openclaw:main",
            "input": "hello",
            "tools": {"type": "function", "name": "calc"},
        },
    )

    assert response.status_code == 400
    assert "tools must be a list" in response.json()["detail"]
    assert called["upstream"] is False


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
    monkeypatch.setattr("agency_swarm.integrations.openclaw._is_upstream_port_open", lambda _config: True)

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

    health_unauthorized = client.get("/openclaw/health")
    assert health_unauthorized.status_code in (401, 403)

    authorized = client.post(
        "/openclaw/v1/responses",
        json={"model": "openclaw:main", "input": "hello"},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert authorized.status_code == 200

    health_authorized = client.get("/openclaw/health", headers={"Authorization": "Bearer secret-token"})
    assert health_authorized.status_code == 200
    assert health_authorized.json() == {"ok": True, "upstream_base_url": "http://127.0.0.1:18789"}


def test_openclaw_normalization_validation_error_paths() -> None:
    with pytest.raises(ValueError, match="model is required"):
        normalize_openclaw_responses_request({"input": "hello"})
    with pytest.raises(ValueError, match="input is required"):
        normalize_openclaw_responses_request({"model": "openclaw:main"})
    with pytest.raises(ValueError, match="input must be a string or list"):
        normalize_openclaw_responses_request({"model": "openclaw:main", "input": {"bad": "shape"}})
    with pytest.raises(ValueError, match="input list items must be JSON objects"):
        normalize_openclaw_responses_request({"model": "openclaw:main", "input": ["bad"]})
    with pytest.raises(ValueError, match="input message role must be a non-empty string"):
        normalize_openclaw_responses_request(
            {"model": "openclaw:main", "input": [{"type": "message", "content": "missing role"}]}
        )
    with pytest.raises(ValueError, match="input message content must be a string or list"):
        normalize_openclaw_responses_request(
            {"model": "openclaw:main", "input": [{"role": "user", "content": {"bad": "shape"}}]}
        )

    normalized = normalize_openclaw_responses_request(
        {
            "model": "openclaw:main",
            "input": "hello",
            "tool_choice": "unsupported",
            "metadata": "bad-metadata",
        }
    )
    assert "tool_choice" not in normalized
    assert "metadata" not in normalized


def test_openclaw_header_helpers() -> None:
    assert openclaw_mod._make_upstream_headers("") == {"Content-Type": "application/json"}
    assert openclaw_mod._make_upstream_headers("token") == {
        "Content-Type": "application/json",
        "Authorization": "Bearer token",
    }

    upstream = httpx.Response(
        status_code=200,
        content=gzip.compress(b"ok"),
        headers={
            "content-type": "application/json",
            "x-request-id": "req-1",
            "content-encoding": "gzip",
            "content-length": "2",
        },
    )
    assert "content-encoding" in openclaw_mod._passthrough_response_headers(upstream, decoded_body=False)
    assert "content-encoding" not in openclaw_mod._passthrough_response_headers(upstream, decoded_body=True)
