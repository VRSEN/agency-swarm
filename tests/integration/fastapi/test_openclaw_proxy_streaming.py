from __future__ import annotations

import json
import socket
import threading
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("fastapi.testclient")
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agency_swarm.integrations.openclaw import attach_openclaw_to_fastapi
from tests.integration.fastapi._openclaw_test_support import _build_openclaw_config


def _reserve_free_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    except PermissionError as exc:
        pytest.skip(f"loopback bind unavailable in this environment: {exc}")


class _OpenClawResponsesStubHandler(BaseHTTPRequestHandler):
    mode = "success"
    requests_seen: list[dict[str, object]] = []

    def log_message(self, *_args, **_kwargs) -> None:  # noqa: D401, N802
        """Silence stub server logs."""

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/responses":
            self.send_response(404)
            self.end_headers()
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        payload = json.loads(raw_body.decode("utf-8"))
        self.__class__.requests_seen.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "payload": payload,
            }
        )

        if self.__class__.mode == "stream-error":
            error_body = b'{"error":"upstream"}'
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(error_body)))
            self.send_header("Retry-After", "5")
            self.end_headers()
            self.wfile.write(error_body)
            return

        if payload.get("stream"):
            stream_body = b'event: data\ndata: {"chunk": 1}\n\nevent: end\ndata: [DONE]\n\n'
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(stream_body)))
            self.send_header("X-Request-Id", "req-stream")
            self.end_headers()
            self.wfile.write(stream_body)
            return

        response = {
            "id": "resp_1",
            "object": "response",
            "model": payload["model"],
            "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]}],
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Request-Id", "req-json")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def openclaw_upstream_server() -> str:
    handler = _OpenClawResponsesStubHandler
    handler.mode = "success"
    handler.requests_seen = []
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    except PermissionError as exc:
        pytest.skip(f"loopback bind unavailable in this environment: {exc}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_openclaw_proxy_nonstream_passthrough_rewrites_default_model(
    openclaw_upstream_server: str, tmp_path: Path
) -> None:
    host, port_text = openclaw_upstream_server.removeprefix("http://").split(":")
    app = FastAPI()
    attach_openclaw_to_fastapi(
        app,
        replace(_build_openclaw_config(tmp_path), host=host, port=int(port_text)),
    )
    client = TestClient(app)

    response = client.post("/openclaw/v1/responses", json={"model": "openclaw:main", "input": "hello"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-json"
    assert response.json()["model"] == "openai/gpt-5.4-mini"
    assert _OpenClawResponsesStubHandler.requests_seen[0]["authorization"] == "Bearer gateway-token"
    assert _OpenClawResponsesStubHandler.requests_seen[0]["payload"]["model"] == "openai/gpt-5.4-mini"


def test_openclaw_proxy_stream_passthrough_uses_upstream_event_stream(
    openclaw_upstream_server: str, tmp_path: Path
) -> None:
    host, port_text = openclaw_upstream_server.removeprefix("http://").split(":")
    app = FastAPI()
    attach_openclaw_to_fastapi(
        app,
        replace(_build_openclaw_config(tmp_path), host=host, port=int(port_text)),
    )
    client = TestClient(app)

    response = client.post("/openclaw/v1/responses", json={"model": "openclaw:main", "input": "hello", "stream": True})

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert response.headers["x-request-id"] == "req-stream"
    assert 'data: {"chunk": 1}' in response.text
    assert _OpenClawResponsesStubHandler.requests_seen[0]["payload"]["model"] == "openai/gpt-5.4-mini"


def test_openclaw_proxy_stream_error_passthrough_preserves_upstream_payload(
    openclaw_upstream_server: str, tmp_path: Path
) -> None:
    host, port_text = openclaw_upstream_server.removeprefix("http://").split(":")
    _OpenClawResponsesStubHandler.mode = "stream-error"
    app = FastAPI()
    attach_openclaw_to_fastapi(
        app,
        replace(_build_openclaw_config(tmp_path), host=host, port=int(port_text)),
    )
    client = TestClient(app)

    response = client.post("/openclaw/v1/responses", json={"model": "openclaw:main", "input": "hello", "stream": True})

    assert response.status_code == 500
    assert response.text == '{"error":"upstream"}'
    assert response.headers["retry-after"] == "5"


def test_openclaw_proxy_reports_health_from_upstream_port(openclaw_upstream_server: str, tmp_path: Path) -> None:
    host, port_text = openclaw_upstream_server.removeprefix("http://").split(":")
    app = FastAPI()
    attach_openclaw_to_fastapi(
        app,
        replace(_build_openclaw_config(tmp_path), host=host, port=int(port_text)),
    )
    client = TestClient(app)

    healthy = client.get("/openclaw/health")

    assert healthy.status_code == 200
    assert healthy.json()["ok"] is True


def test_openclaw_proxy_health_returns_503_when_upstream_port_is_closed(tmp_path: Path) -> None:
    closed_port = _reserve_free_port()
    app = FastAPI()
    attach_openclaw_to_fastapi(app, replace(_build_openclaw_config(tmp_path), port=closed_port))
    client = TestClient(app)

    unhealthy = client.get("/openclaw/health")

    assert unhealthy.status_code == 503
    assert unhealthy.json()["ok"] is False


def test_openclaw_proxy_rejects_invalid_json_body(tmp_path: Path) -> None:
    app = FastAPI()
    attach_openclaw_to_fastapi(app, _build_openclaw_config(tmp_path))
    client = TestClient(app)

    response = client.post("/openclaw/v1/responses", data="{bad", headers={"content-type": "application/json"})

    assert response.status_code == 400
    assert "Invalid JSON body" in response.json()["detail"]
