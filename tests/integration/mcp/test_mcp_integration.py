import asyncio
import logging
import os

import pytest
from agents import ModelSettings
from agents.mcp.server import MCPServerStdio
from dotenv import load_dotenv

from agency_swarm import Agency, Agent

load_dotenv(override=True)

logger = logging.getLogger(__name__)


def _stdio_server_path() -> str:
    # Use the test stdio server script bundled in tests/data/scripts
    this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(this_dir, "..", "..", "data", "scripts", "stdio_server.py"))


def _agency_factory() -> Agency:
    stdio_server = MCPServerStdio(
        name="Test_STDIO_Server",
        params={
            "command": "python",
            "args": [_stdio_server_path()],
        },
        client_session_timeout_seconds=15,
    )

    agent = Agent(
        name="MCP StdIO Agent",
        model_settings=ModelSettings(temperature=0),
        mcp_servers=[stdio_server],
    )

    return Agency(
        agent,
        name="mcp_stdio_agency",
        user_context={"session_id": "mcp_stdio_session"},
        shared_instructions="Test MCP StdIO Integration",
    )


@pytest.mark.asyncio
async def test_mcp_stdio_get_response(caplog):
    agency = _agency_factory()

    with caplog.at_level(logging.ERROR):
        res = await agency.get_response("What tools do you have?")

    assert "greet" in res.final_output.lower() and "add" in res.final_output.lower()

    # ensure no MCP cleanup error logs were emitted
    err_msgs = [rec.getMessage() for rec in caplog.records]
    assert not any(
        ("Attempted to exit cancel scope in a different task than it was entered in" in msg)
        or ("Error cleaning up server:" in msg)
        for msg in err_msgs
    ), f"Found MCP cleanup error logs: {err_msgs}"


@pytest.mark.asyncio
async def test_mcp_stdio_get_response_stream(caplog):
    agency = _agency_factory()

    saw_any_event = False
    saw_error = False

    async def _consume_stream():
        nonlocal saw_any_event, saw_error
        async for ev in agency.get_response_stream("What tools do you have?"):
            saw_any_event = True
            if isinstance(ev, dict) and ev.get("type") == "error":
                saw_error = True

    with caplog.at_level(logging.ERROR):
        try:
            await asyncio.wait_for(_consume_stream(), timeout=30)
        except asyncio.TimeoutError:  # noqa: UP041
            pytest.fail("Streaming timed out; possible hang in MCP streaming handling")

    assert saw_any_event, "Expected at least one streaming event"
    assert not saw_error, "Received error event during MCP streaming"

    # ensure no MCP cleanup error logs were emitted
    err_msgs = [rec.getMessage() for rec in caplog.records]
    assert not any(
        ("Attempted to exit cancel scope in a different task than it was entered in" in msg)
        or ("Error cleaning up server:" in msg)
        for msg in err_msgs
    ), f"Found MCP cleanup error logs: {err_msgs}"
