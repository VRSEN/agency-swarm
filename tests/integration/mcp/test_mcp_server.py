"""
Integration test for the MCP HTTP server using run_mcp and HostedMCPTool.

This test spins up the MCP server over streamable-http, then verifies that an
Agent configured with a HostedMCPTool can discover available tools and invoke
one of them.
"""

import logging
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from agents import ModelSettings
from agents.mcp.server import (
    MCPServerStdio,
    MCPServerStdioParams,
    MCPServerStreamableHttp,
    MCPServerStreamableHttpParams,
)

from agency_swarm import Agency, Agent, run_mcp
from tests.data.tools.sample_tool import sample_tool


def _tools_dir() -> str:
    # Use sample tools bundled with tests
    return str(Path(__file__).parents[2] / "data" / "tools")


def _reserve_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def mcp_http_server():
    """Start MCP tools server over HTTP in a background thread."""

    port = _reserve_port()
    server_url = f"http://127.0.0.1:{port}"

    def _run_server():
        # Disable auth for the test by using an empty env var name
        run_mcp(
            tools=_tools_dir(),
            host="127.0.0.1",
            port=port,
            app_token_env="",  # no auth
            server_name="mcp-tools-server",
            transport="streamable-http",
        )

    thread = threading.Thread(target=_run_server, daemon=True)
    thread.start()

    # Wait for server to start
    max_retries = 30
    for i in range(max_retries):
        try:
            # Any response indicates the server is listening; endpoint may not be GET-able
            resp = httpx.get(server_url + "/mcp", timeout=2.0)
            if resp.status_code in (200, 400, 404, 405):
                # Give it a brief moment more to fully initialize
                time.sleep(0.5)
                break
        except Exception:
            time.sleep(0.5)
            if i == max_retries - 1:
                pytest.skip("Could not start MCP HTTP server")

    yield server_url
    # No explicit shutdown; thread is daemon and server ends with process


def _make_agency_with_local_mcp(server_url: str) -> Agency:
    """Create an Agency with a local MCP client pointing to the HTTP server."""
    mcp_client = MCPServerStreamableHttp(
        name="Local_MCP_Server",
        params=MCPServerStreamableHttpParams(
            url=server_url + "/mcp",
            headers={},
        ),
        cache_tools_list=True,
    )

    agent = Agent(
        name="MCP HTTP Agent",
        description="Agent using local MCP tools over HTTP",
        mcp_servers=[mcp_client],
        model_settings=ModelSettings(temperature=0),
    )

    return Agency(agent, name="mcp_http_agency", shared_instructions="Test MCP HTTP Integration")


@pytest.mark.asyncio
async def test_mcp_http_tools_list(mcp_http_server):
    """Verify the agent can discover tools exposed by the MCP HTTP server."""
    agency = _make_agency_with_local_mcp(mcp_http_server)
    res = await agency.get_response("What tools do you have?")
    text = str(res.final_output).lower()
    # sample_tool is provided by tests/data/tools/sample_tool.py
    normalized = text.replace(" ", "_")
    assert "sample_tool" in normalized


@pytest.mark.asyncio
async def test_mcp_http_invoke_sample_tool(mcp_http_server):
    """Verify the agent can invoke a local MCP tool over HTTP."""
    agency = _make_agency_with_local_mcp(mcp_http_server)
    res = await agency.get_response("Use sample_tool to echo 'hello mcp'.")
    assert "echo" in str(res.final_output).lower()


@pytest.mark.asyncio
async def test_mcp_http_error_cases():
    """Test error handling in run_mcp function."""

    # Test empty tools list
    with pytest.raises(ValueError, match="No tools provided"):
        run_mcp(tools=[], return_app=True)

    # Test empty directory
    empty_dir = Path(__file__).parent / "empty_test_dir"
    empty_dir.mkdir(exist_ok=True)
    try:
        with pytest.raises(ValueError, match="No BaseTool classes found in directory"):
            run_mcp(tools=str(empty_dir), return_app=True)
    finally:
        empty_dir.rmdir()

    # Test duplicate tool names
    duplicate_tool = sample_tool  # Same tool twice
    with pytest.raises(ValueError, match="Duplicate tool name detected"):
        run_mcp(tools=[sample_tool, duplicate_tool], return_app=True)


@pytest.mark.asyncio
async def test_mcp_stdio_server_integration():
    """Test MCP stdio server integration with agent."""

    # Create a temporary MCP server script with inline tool definition
    server_script = """
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents import function_tool
from agency_swarm.integrations.mcp_server import run_mcp

@function_tool
def test_sample_tool(text: str) -> str:
    \"\"\"Echo tool that returns the input text.\"\"\"
    return f"Echo: {text}"

if __name__ == "__main__":
    run_mcp(tools=[test_sample_tool], transport="stdio")
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(server_script)
        server_path = f.name

    try:
        # Set up MCP client pointing to our stdio server
        stdio_server = MCPServerStdio(
            name="Test_Stdio_Server",
            params=MCPServerStdioParams(
                command=sys.executable,
                args=[server_path],
            ),
            client_session_timeout_seconds=10,
        )

        agent = Agent(
            name="MCP Stdio Agent",
            model_settings=ModelSettings(temperature=0),
            mcp_servers=[stdio_server],
        )

        agency = Agency(
            agent,
            name="mcp_stdio_test_agency",
            shared_instructions="Test MCP stdio server integration",
        )

        # Test that agent can list tools from stdio server
        res = await agency.get_response("What tools do you have available?")
        response_text = str(res.final_output).lower()

        # Should find test_sample_tool from our stdio server
        normalized = response_text.replace(" ", "_")
        assert "test_sample_tool" in normalized

    finally:
        # Cleanup
        Path(server_path).unlink(missing_ok=True)


def test_mcp_with_auth_token():
    """Test authentication middleware setup."""

    # Set a test token
    os.environ["TEST_MCP_TOKEN"] = "test-token-123"
    try:
        app = run_mcp(tools=[sample_tool], app_token_env="TEST_MCP_TOKEN", transport="streamable-http", return_app=True)
        assert app is not None

        # Verify auth middleware was actually added
        assert len(app.middleware) > 0, "Auth middleware should be added when token is provided"
        middleware = app.middleware[0]

        # Check that it's the StaticBearer middleware with correct token
        assert hasattr(middleware, "expected"), "Middleware should have 'expected' attribute"
        assert middleware.expected == "Bearer test-token-123", "Middleware should expect correct Bearer token"
    finally:
        del os.environ["TEST_MCP_TOKEN"]


def test_mcp_stdio_with_auth_warning(caplog):
    """Test stdio transport with auth warning."""

    # Set a test token for stdio (should trigger warning)
    os.environ["TEST_STDIO_TOKEN"] = "test-token-456"
    try:
        with caplog.at_level(logging.WARNING):
            app = run_mcp(tools=[sample_tool], app_token_env="TEST_STDIO_TOKEN", transport="stdio", return_app=True)
        assert app is not None
        assert any("Stdio servers do not support authentication" in record.message for record in caplog.records)
    finally:
        del os.environ["TEST_STDIO_TOKEN"]


def test_mcp_unsupported_tool_type():
    """Test unsupported tool type error."""

    # Create a mock tool that's neither BaseTool nor FunctionTool
    class UnsupportedTool:
        name = "unsupported_tool"

    with pytest.raises(ValueError, match="Unexpected tool type"):
        run_mcp(tools=[UnsupportedTool()], return_app=True)


def test_mcp_base_tool_conversion():
    """Test BaseTool to FunctionTool conversion."""
    from pydantic import Field

    from agency_swarm import BaseTool
    from agency_swarm.integrations.mcp_server import run_mcp

    class TestBaseTool(BaseTool):
        """A test BaseTool for conversion testing."""

        input_text: str = Field(..., description="Input text")

        def run(self):
            return f"BaseTool result: {self.input_text}"

    app = run_mcp(tools=[TestBaseTool], return_app=True)
    assert app is not None


@pytest.mark.asyncio
async def test_mcp_auth_middleware_methods():
    """Test authentication middleware on_request and on_read_resource methods."""

    # Set up environment for auth
    os.environ["TEST_AUTH_TOKEN"] = "test-auth-token"
    try:
        app = run_mcp(
            tools=[sample_tool], app_token_env="TEST_AUTH_TOKEN", transport="streamable-http", return_app=True
        )

        # Get the auth middleware that was added
        middleware = app.middleware[0] if app.middleware else None
        assert middleware is not None

        # Test on_request method with correct auth
        mock_ctx = MagicMock()
        mock_call_next = AsyncMock(return_value="success")

        # Test with correct authorization header by patching the module where it's imported
        with patch(
            "agency_swarm.integrations.mcp_server.get_http_headers",
            return_value={"authorization": "Bearer test-auth-token"},
        ):
            result = await middleware.on_request(mock_ctx, mock_call_next)
            assert result == "success"
            mock_call_next.assert_called_once()

            # Test on_read_resource method with correct auth
            mock_call_next.reset_mock()
            result = await middleware.on_read_resource(mock_ctx, mock_call_next)
            assert result == "success"
            mock_call_next.assert_called_once()

        # Test with incorrect authorization (should raise McpError)
        mock_call_next.reset_mock()
        with patch(
            "agency_swarm.integrations.mcp_server.get_http_headers",
            return_value={"authorization": "Bearer wrong-token"},
        ):
            from fastmcp.exceptions import McpError

            with pytest.raises(McpError):
                await middleware.on_request(mock_ctx, mock_call_next)

            with pytest.raises(McpError):
                await middleware.on_read_resource(mock_ctx, mock_call_next)

    finally:
        del os.environ["TEST_AUTH_TOKEN"]
