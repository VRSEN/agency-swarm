"""Unmocked HTTP and ASGI authentication tests for run_mcp()."""

import json
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx2
import pytest
import uvicorn
from agents.mcp.server import (
    MCPServerSse,
    MCPServerSseParams,
    MCPServerStreamableHttp,
    MCPServerStreamableHttpParams,
)

from agency_swarm import run_mcp
from tests.data.tools.sample_tool import sample_tool

_INIT_PARAMS: dict[str, Any] = {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "auth-test", "version": "1.0"},
}

_PROBE_REQUESTS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("initialize", _INIT_PARAMS),
    ("tools/list", {}),
    ("tools/call", {"name": "sample_tool", "arguments": {"text": "hello auth"}}),
    ("resources/read", {"uri": "resource://protected"}),
)


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _run_uvicorn_app(app: Any) -> Iterator[str]:
    port = _reserve_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started, "Uvicorn MCP server did not start in time"
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _parse_mcp_jsonrpc(response: httpx2.Response) -> dict[str, Any]:
    """Parse a Streamable HTTP response returned as JSON or SSE."""
    if "text/event-stream" in response.headers.get("content-type", ""):
        for line in response.text.splitlines():
            if line.startswith("data: "):
                return json.loads(line.removeprefix("data: "))
        raise AssertionError(f"No SSE data payload in response: {response.text!r}")
    return response.json()


async def _post_mcp_jsonrpc(
    client: httpx2.AsyncClient,
    method: str,
    params: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    response = await client.post(
        "/mcp",
        headers=request_headers,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )
    assert response.status_code == 200, response.text
    return _parse_mcp_jsonrpc(response)


def _exception_mentions_unauthorized(exc: BaseException) -> bool:
    if "Unauthorized" in str(exc) or "Unauthorized" in repr(exc):
        return True
    if isinstance(exc, BaseExceptionGroup) and any(_exception_mentions_unauthorized(sub) for sub in exc.exceptions):
        return True
    if exc.__cause__ is not None and _exception_mentions_unauthorized(exc.__cause__):
        return True
    if exc.__context__ is not None and _exception_mentions_unauthorized(exc.__context__):
        return True
    return False


def _build_protected_app(monkeypatch: pytest.MonkeyPatch, env_var: str, token: str, transport: str) -> Any:
    monkeypatch.setenv(env_var, token)
    mcp = run_mcp(tools=[sample_tool], app_token_env=env_var, transport=transport, return_app=True)
    assert mcp is not None

    @mcp.resource("resource://protected")
    def protected_resource() -> str:
        return "protected-secret-content"

    return mcp.http_app(transport=transport)


@pytest.mark.asyncio
async def test_run_mcp_http_bearer_auth_accepts_valid_token_and_rejects_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unmocked ASGI requests enforce Bearer auth for initialize, tools, and protected resources."""
    http_app = _build_protected_app(monkeypatch, "TEST_AUTH_TOKEN", "test-auth-token", "streamable-http")
    valid_headers = {"Authorization": "Bearer test-auth-token"}

    async with http_app.router.lifespan_context(http_app):
        transport = httpx2.ASGITransport(app=http_app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as client:
            init_body = await _post_mcp_jsonrpc(client, *_PROBE_REQUESTS[0], headers=valid_headers)
            assert "protocolVersion" in init_body["result"], init_body

            tools_body = await _post_mcp_jsonrpc(
                client, *_PROBE_REQUESTS[1], headers={"authorization": "Bearer test-auth-token"}
            )
            assert any(tool["name"] == "sample_tool" for tool in tools_body["result"]["tools"])

            call_body = await _post_mcp_jsonrpc(client, *_PROBE_REQUESTS[2], headers=valid_headers)
            assert any("Echo: hello auth" in item.get("text", "") for item in call_body["result"]["content"])

            resource_body = await _post_mcp_jsonrpc(client, *_PROBE_REQUESTS[3], headers=valid_headers)
            assert any(item.get("text") == "protected-secret-content" for item in resource_body["result"]["contents"])

            for bad_headers in ({"Authorization": "Bearer wrong-token"}, {}):
                for method, params in _PROBE_REQUESTS:
                    rejected = await _post_mcp_jsonrpc(client, method, params, headers=bad_headers)
                    assert rejected.get("error") == {"code": 401, "message": "Unauthorized"}, (method, rejected)


@pytest.mark.asyncio
@pytest.mark.parametrize("app_token_env", ["TEST_UNSET_MCP_TOKEN", None])
async def test_run_mcp_http_without_token_allows_unauthenticated_requests(
    monkeypatch: pytest.MonkeyPatch, app_token_env: str | None
) -> None:
    """When no token is configured, run_mcp() HTTP servers serve requests without authentication."""
    monkeypatch.delenv("TEST_UNSET_MCP_TOKEN", raising=False)
    mcp = run_mcp(tools=[sample_tool], app_token_env=app_token_env, transport="streamable-http", return_app=True)
    assert mcp is not None

    http_app = mcp.http_app(transport="streamable-http")
    async with http_app.router.lifespan_context(http_app):
        transport = httpx2.ASGITransport(app=http_app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as client:
            init_body = await _post_mcp_jsonrpc(client, *_PROBE_REQUESTS[0])
            assert "protocolVersion" in init_body["result"], init_body

            call_body = await _post_mcp_jsonrpc(
                client, "tools/call", {"name": "sample_tool", "arguments": {"text": "open"}}
            )
            assert any("Echo: open" in item.get("text", "") for item in call_body["result"]["content"])


@pytest.mark.asyncio
async def test_run_mcp_streamable_http_auth_with_sdk_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """A live Streamable HTTP server accepts the valid Bearer token and rejects wrong or missing tokens."""
    http_app = _build_protected_app(monkeypatch, "TEST_LIVE_HTTP_TOKEN", "live-secret-token", "streamable-http")

    with _run_uvicorn_app(http_app) as base_url:
        url = f"{base_url}/mcp"
        async with MCPServerStreamableHttp(
            name="Authorized_HTTP",
            params=MCPServerStreamableHttpParams(url=url, headers={"Authorization": "Bearer live-secret-token"}),
        ) as client:
            assert any(tool.name == "sample_tool" for tool in await client.list_tools())
            result = await client.call_tool("sample_tool", {"text": "over-http"})
            assert any(getattr(item, "text", "") == "Echo: over-http" for item in result.content)

        for bad_headers in ({"Authorization": "Bearer wrong-token"}, {}):
            with pytest.raises(BaseException) as exc_info:
                async with MCPServerStreamableHttp(
                    name="Unauthorized_HTTP",
                    params=MCPServerStreamableHttpParams(url=url, headers=bad_headers),
                ) as client:
                    await client.list_tools()
            assert _exception_mentions_unauthorized(exc_info.value), exc_info.value


@pytest.mark.asyncio
async def test_run_mcp_sse_auth_with_sdk_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """A live SSE server accepts the valid Bearer token and rejects wrong or missing tokens."""
    http_app = _build_protected_app(monkeypatch, "TEST_LIVE_SSE_TOKEN", "sse-secret-token", "sse")

    with _run_uvicorn_app(http_app) as base_url:
        url = f"{base_url}/sse"
        async with MCPServerSse(
            name="Authorized_SSE",
            params=MCPServerSseParams(url=url, headers={"Authorization": "Bearer sse-secret-token"}),
        ) as client:
            assert any(tool.name == "sample_tool" for tool in await client.list_tools())
            result = await client.call_tool("sample_tool", {"text": "over-sse"})
            assert any(getattr(item, "text", "") == "Echo: over-sse" for item in result.content)

        for bad_headers in ({"Authorization": "Bearer wrong-token"}, {}):
            with pytest.raises(BaseException) as exc_info:
                async with MCPServerSse(
                    name="Unauthorized_SSE",
                    params=MCPServerSseParams(url=url, headers=bad_headers),
                ) as client:
                    await client.list_tools()
            assert _exception_mentions_unauthorized(exc_info.value), exc_info.value
