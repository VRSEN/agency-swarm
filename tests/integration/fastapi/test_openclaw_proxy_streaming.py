from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest

pytest.importorskip("fastapi.testclient")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agency_swarm.integrations.openclaw import attach_openclaw_to_fastapi
from tests.integration.fastapi._openclaw_test_support import _build_openclaw_config


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


def test_openclaw_stream_connect_uses_bounded_connect_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeStreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        async def aiter_raw(self):
            yield b"event: end\ndata: [DONE]\n\n"

    class _FakeStreamContext:
        async def __aenter__(self) -> _FakeStreamResponse:
            return _FakeStreamResponse()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class _FakeAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["timeout"] = kwargs.get("timeout")

        def stream(self, method: str, url: str, *, headers: dict[str, str], json: dict[str, Any]) -> _FakeStreamContext:
            return _FakeStreamContext()

        async def aclose(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr("agency_swarm.integrations.openclaw.httpx.AsyncClient", _FakeAsyncClient)

    config = replace(_build_openclaw_config(tmp_path), proxy_timeout_seconds=7.5)
    app = FastAPI()
    attach_openclaw_to_fastapi(app, config)
    client = TestClient(app)

    response = client.post(
        "/openclaw/v1/responses",
        json={"model": "openclaw:main", "input": "hello", "stream": True},
    )

    assert response.status_code == 200
    assert isinstance(captured["timeout"], httpx.Timeout)
    assert captured["timeout"].connect == pytest.approx(7.5)
    assert captured["timeout"].read is None
    assert captured["timeout"].write == pytest.approx(7.5)
    assert captured["timeout"].pool == pytest.approx(7.5)
    assert captured["closed"] is True


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


def test_openclaw_stream_connect_non_http_error_closes_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {"closed": False}

    class _FailingStreamContext:
        async def __aenter__(self) -> None:
            raise RuntimeError("stream boot failed")

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

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
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/openclaw/v1/responses",
        json={"model": "openclaw:main", "input": "hello", "stream": True},
    )

    assert response.status_code == 500
    assert captured["closed"] is True
