"""End-to-end regression tests for MCP OAuth discovery and persistence."""

import asyncio
import inspect
import json
import logging
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from agents.tool_context import ToolContext

from agency_swarm import Agency, Agent
from agency_swarm.mcp.oauth import (
    FileTokenStorage,
    MCPServerOAuth,
    OAuthCallbackHandler,
    OAuthRedirectHandler,
    OAuthStorageHooks,
)
from agency_swarm.mcp.oauth_client import MCPServerOAuthClient
from agency_swarm.tools.mcp_manager import default_mcp_manager


@dataclass
class _OAuthServerState:
    registration_scopes: list[str | None] = field(default_factory=list)
    authorization_scopes: list[str | None] = field(default_factory=list)


class _OAuthTestServer(HTTPServer):
    state: _OAuthServerState
    base_url: str

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _OAuthRequestHandler)
        host, port = cast("tuple[str, int]", self.server_address)
        self.base_url = f"http://{host}:{port}"
        self.state = _OAuthServerState()


class _OAuthRequestHandler(BaseHTTPRequestHandler):
    server: _OAuthTestServer

    def log_message(self, format: str, *args: object) -> None:
        """Keep the regression test output quiet."""

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        return cast("dict[str, object]", json.loads(self.rfile.read(length)))

    def _read_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        values = parse_qs(self.rfile.read(length).decode())
        return {key: items[0] for key, items in values.items()}

    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_unauthorized(self) -> None:
        metadata_url = f"{self.server.base_url}/.well-known/oauth-protected-resource/mcp"
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Bearer resource_metadata="{metadata_url}"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path == "/.well-known/oauth-protected-resource/mcp":
            self._send_json(
                200,
                {
                    "resource": f"{self.server.base_url}/mcp",
                    "authorization_servers": [self.server.base_url],
                    "scopes_supported": ["treasure.read"],
                },
            )
            return
        if parsed.path == "/.well-known/oauth-authorization-server":
            self._send_json(
                200,
                {
                    "issuer": self.server.base_url,
                    "authorization_endpoint": f"{self.server.base_url}/authorize",
                    "token_endpoint": f"{self.server.base_url}/token",
                    "registration_endpoint": f"{self.server.base_url}/register",
                    "response_types_supported": ["code"],
                    "grant_types_supported": ["authorization_code", "refresh_token"],
                    "code_challenge_methods_supported": ["S256"],
                    "token_endpoint_auth_methods_supported": ["none"],
                    "scopes_supported": ["treasure.read", "user"],
                },
            )
            return
        if parsed.path == "/authorize":
            query = parse_qs(parsed.query)
            scope = query.get("scope", [None])[0]
            state = query["state"][0]
            redirect_uri = query["redirect_uri"][0]
            self.server.state.authorization_scopes.append(scope)
            callback_query = urlencode({"code": "test-code", "state": state})
            self.send_response(302)
            self.send_header("Location", f"{redirect_uri}?{callback_query}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if parsed.path == "/mcp":
            self._send_empty(405)
            return
        self._send_empty(404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path == "/register":
            registration = self._read_json()
            scope = registration.get("scope")
            self.server.state.registration_scopes.append(scope if isinstance(scope, str) else None)
            registration.update(
                {
                    "client_id": "test-client",
                    "client_id_issued_at": 1,
                    "token_endpoint_auth_method": "none",
                }
            )
            self._send_json(201, registration)
            return
        if parsed.path == "/token":
            token_request = self._read_form()
            if token_request.get("code") != "test-code":
                self._send_json(400, {"error": "invalid_grant"})
                return
            self._send_json(
                200,
                {
                    "access_token": "test-access-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": self.server.state.authorization_scopes[-1],
                },
            )
            return
        if parsed.path != "/mcp":
            self._send_empty(404)
            return
        if self.headers.get("Authorization") != "Bearer test-access-token":
            self._send_unauthorized()
            return

        request = self._read_json()
        request_id = request.get("id")
        method = request.get("method")
        if request_id is None:
            self._send_empty(202)
            return
        if method == "initialize":
            self._send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "oauth-test-server", "version": "1.0"},
                    },
                },
            )
            return
        if method == "tools/list":
            self._send_json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": [
                            {
                                "name": "open_treasure",
                                "description": "Open the test treasure.",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                        ]
                    },
                },
            )
            return
        self._send_json(
            200,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": "Method not found"},
            },
        )

    def do_DELETE(self) -> None:  # noqa: N802
        self._send_empty(204)


@pytest.fixture
def oauth_server() -> Iterator[_OAuthTestServer]:
    server = _OAuthTestServer()
    thread = threading.Thread(target=server.serve_forever, name="oauth-regression-server", daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        assert not thread.is_alive()


def _headless_handlers(
    server: _OAuthTestServer,
) -> tuple[OAuthRedirectHandler, OAuthCallbackHandler]:
    callback_url: str | None = None

    async def redirect_handler(auth_url: str) -> None:
        nonlocal callback_url
        async with httpx.AsyncClient(follow_redirects=False) as client:
            response = await client.get(auth_url)
        if not response.is_redirect:
            response.raise_for_status()
        callback_url = response.headers["Location"]

    async def callback_handler() -> tuple[str, str | None]:
        if callback_url is None:
            raise RuntimeError("Authorization redirect did not produce a callback URL")
        query = parse_qs(urlsplit(callback_url).query)
        return query["code"][0], query.get("state", [None])[0]

    return redirect_handler, callback_handler


def _oauth_config(
    server: _OAuthTestServer,
    cache_dir: Path,
    *,
    scopes: list[str] | None,
) -> MCPServerOAuth:
    redirect_handler, callback_handler = _headless_handlers(server)
    return MCPServerOAuth(
        url=f"{server.base_url}/mcp",
        name="treasury",
        scopes=scopes,
        redirect_uri="http://127.0.0.1/callback",
        cache_dir=cache_dir,
        use_env_credentials=False,
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
    )


@asynccontextmanager
async def _connected_client(config: MCPServerOAuth) -> AsyncIterator[MCPServerOAuthClient]:
    client = MCPServerOAuthClient(config)
    try:
        tools = await client.list_tools()
        assert [tool.name for tool in tools] == ["open_treasure"]
        yield client
    finally:
        await client.cleanup()


def test_documented_agency_oauth_wiring_runs(tmp_path: Path) -> None:
    """The docstring form should use Agency's automatic OAuth storage hook."""
    docstring = inspect.getdoc(OAuthStorageHooks)
    assert docstring is not None
    assert "hooks=[" not in docstring

    agent = Agent(
        name="OAuthAgent",
        instructions="Use OAuth MCP tools.",
        mcp_servers=[MCPServerOAuth(url="http://127.0.0.1:8001/mcp", name="treasury")],
    )
    agency = Agency(
        agent,
        oauth_token_path=str(tmp_path),
        user_context={"user_id": "user_123"},
    )

    assert agency.default_run_hooks is not None


@pytest.mark.asyncio
async def test_token_storage_error_survives_agent_oauth_activation(
    oauth_server: _OAuthTestServer,
    tmp_path: Path,
) -> None:
    """The agent result should name the token-file failure, not a transport cancellation."""
    config = _oauth_config(oauth_server, tmp_path, scopes=["user"])
    storage = FileTokenStorage(
        cache_dir=tmp_path,
        server_name=config.name,
        server_url=config.url,
        client_identity=config.get_client_identity(),
    )
    token_path = tmp_path / "default" / storage.server_cache_segment / "tokens.json"
    token_path.mkdir(parents=True)
    agent = Agent(name="OAuthAgent", instructions="Use OAuth MCP tools.", mcp_servers=[config])
    activation_tool = next(tool for tool in agent.tools if tool.name == "authenticate_mcp_server")
    context = ToolContext(
        context=SimpleNamespace(agent_runtime_state={}, user_context={}),
        tool_name="authenticate_mcp_server",
        tool_call_id="call-1",
        tool_arguments="{}",
    )

    try:
        result = await asyncio.wait_for(
            activation_tool.on_invoke_tool(context, '{"server_name":"treasury"}'),
            timeout=10,
        )
    finally:
        await default_mcp_manager.shutdown()

    assert "Failed to authenticate MCP server 'treasury'" in result
    assert "Is a directory" in result
    assert str(token_path) in result
    assert "was cancelled" not in result


@pytest.mark.asyncio
async def test_explicit_scopes_reach_registration_and_authorization(
    oauth_server: _OAuthTestServer,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Explicit scopes should stay authoritative when discovery advertises another scope."""
    config = _oauth_config(oauth_server, tmp_path, scopes=["user"])

    with caplog.at_level(logging.WARNING):
        async with _connected_client(config):
            pass

    assert oauth_server.state.registration_scopes == ["user"]
    assert oauth_server.state.authorization_scopes == ["user"]
    assert "not advertised" in caplog.text
    assert "treasure.read" in caplog.text


@pytest.mark.asyncio
async def test_discovery_scopes_are_default_when_scopes_are_omitted(
    oauth_server: _OAuthTestServer,
    tmp_path: Path,
) -> None:
    """Discovery should supply scopes only when the config leaves them unset."""
    config = _oauth_config(oauth_server, tmp_path, scopes=None)

    async with _connected_client(config):
        pass

    assert oauth_server.state.registration_scopes == ["treasure.read"]
    assert oauth_server.state.authorization_scopes == ["treasure.read"]
