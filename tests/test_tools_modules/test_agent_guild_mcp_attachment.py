"""Prove native initialization ordering with actual MCP/Agent classes, replacing HTTP only."""

import asyncio
import json

import httpx

from agency_swarm import FunctionTool
from agency_swarm.tools.mcp_manager import default_mcp_manager
from examples.agent_guild_observation import (
    Result,
    attach_selected_endpoint,
    create_observer_agent,
    observe_with_native_tool,
)
from tests.test_tools_modules.test_agent_guild_observation import TARGET, configured, http_response


def test_actual_mcp_initialization_follows_only_separate_host_attachment() -> None:
    events: list[tuple[str, str]] = []

    def guild(request: httpx.Request) -> httpx.Response:
        events.append(("observation", str(request.url)))
        return http_response()

    def mcp(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == str(httpx.URL(TARGET))
        assert "authorization" not in request.headers
        if request.method != "POST":
            events.append((request.method, str(request.url)))
            return httpx.Response(405)
        message = json.loads(request.content)
        method = message["method"]
        events.append((method, str(request.url)))
        if "id" not in message:
            return httpx.Response(202)
        if method == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "synthetic-public-endpoint", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "synthetic_echo",
                        "description": "Synthetic discovery metadata; no call is made",
                        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                    }
                ]
            }
        else:
            raise AssertionError("No tool execution or unexpected method is authorized by this test")
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": result})

    tool = configured(httpx.MockTransport(guild))
    observer = create_observer_agent(tool)
    assert len(observer.tools) == 1 and isinstance(observer.tools[0], FunctionTool)
    assert not observer.mcp_servers and not events
    result = Result.model_validate_json(asyncio.run(observe_with_native_tool(TARGET, tool)))
    assert result.status == "observed"
    assert [event for event, _ in events] == ["observation"]
    try:
        attached = attach_selected_endpoint(TARGET, transport=httpx.MockTransport(mcp))
        assert any(isinstance(item, FunctionTool) and "synthetic_echo" in item.name for item in attached.tools)
        methods = [event for event, _ in events]
        assert methods[0] == "observation"
        assert "initialize" in methods[1:] and "tools/list" in methods[1:]
        assert "tools/call" not in methods
        # MCP is converted to tools and cleared; empty mcp_servers alone is not
        # evidence that the attached Agent never connected.
        assert attached.mcp_servers == []
    finally:
        default_mcp_manager.shutdown_sync()


def test_invalid_host_attachment_stops_before_native_connection() -> None:
    requests: list[httpx.Request] = []
    try:
        attach_selected_endpoint(
            "http://127.0.0.1/",
            transport=httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(500)),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Private literal should be rejected")
    assert not requests
