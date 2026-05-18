"""Run an agency with a local MCP server and an opt-in hosted MCP server.

This example connects to the pre-made MCP servers with custom tools
that can be found at examples/utils/stdio_mcp_server.py and examples/utils/sse_mcp_server.py

The local stdio MCP server runs automatically and is the default proof path.

The hosted MCP path is optional because OpenAI must reach your MCP server over
the public internet. To test it, run the SSE server on port 8000 behind a public
tunnel, then set MCP_PUBLIC_SERVER_URL to the public URL including /sse.

You can set a custom APP_TOKEN in .env for auth; otherwise this example uses
"test_token_123".

Run the example with: python examples/mcp_servers.py
It will ask the agent to use the local MCP tools and assert the tool outputs.

To enable the hosted MCP server example (copy/paste):
1) Start ngrok in one terminal:
ngrok http 8000

2) In another terminal (replace YOUR_NGROK_ID):
MCP_PUBLIC_SERVER_URL="https://YOUR_NGROK_ID.ngrok-free.app/sse" python examples/mcp_servers.py
"""

import asyncio
import os
import subprocess
import sys
import time

from agents.mcp.server import MCPServerStdio, MCPServerStdioParams
from dotenv import load_dotenv

from agency_swarm import Agency, Agent, HostedMCPTool

load_dotenv()

_EXAMPLES_DIR = os.path.dirname(os.path.abspath(__file__))
_STDIO_SERVER_PATH = os.path.join(_EXAMPLES_DIR, "utils", "stdio_mcp_server.py")
_SSE_SERVER_PATH = os.path.join(_EXAMPLES_DIR, "utils", "sse_mcp_server.py")

app_token = os.getenv("APP_TOKEN")
if not app_token:
    os.environ["APP_TOKEN"] = "test_token_123"
    app_token = "test_token_123"

stdio_server = MCPServerStdio(
    MCPServerStdioParams(command=sys.executable, args=[_STDIO_SERVER_PATH], env={"APP_TOKEN": app_token}),
    cache_tools_list=True,
)


# Launch the SSE MCP server
def launch_sse_server() -> subprocess.Popen[bytes]:
    """Launch the SSE MCP server in a separate process"""
    env = os.environ.copy()
    env["APP_TOKEN"] = app_token

    process = subprocess.Popen(
        [sys.executable, _SSE_SERVER_PATH],
        env=env,
    )

    # Give the server time to start
    time.sleep(2)
    return process


def _function_outputs(agency: Agency) -> list[str]:
    """Return persisted function outputs from the last agency run."""
    outputs: list[str] = []
    for message in agency.thread_manager.get_all_messages():
        if not isinstance(message, dict) or message.get("type") != "function_call_output":
            continue
        outputs.append(str(message.get("output", "")))
    return outputs


def _require_text(haystack: str, needles: list[str], proof_name: str) -> None:
    missing = [needle for needle in needles if needle not in haystack]
    if missing:
        raise RuntimeError(f"{proof_name} did not return required evidence: {missing}")


def _stop_sse_server(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


mcp_agent_local = Agent(
    name="local_MCP_Agent",
    instructions="You are a helpful assistant",
    description="Helpful assistant",
    model="gpt-5.4-mini",
    mcp_servers=[stdio_server],  # <- local mcp server
)

agency_local = Agency(mcp_agent_local)


async def local_mcp_server_example() -> None:
    # Agent will handle execution lifecycle of the MCP server automatically.
    print("Running local MCP server example")
    print("-" * 25)
    message = "Get unique id and then current time in Europe/Amsterdam"
    print(f"Sending message: {message}")
    response = await agency_local.get_response(message)
    print(f"Answer: {response.final_output}")
    proof_text = "\n".join([str(response.final_output), *_function_outputs(agency_local)])
    _require_text(
        proof_text,
        ["Unique ID: 12332211", "Current time in Europe/Amsterdam"],
        "Local MCP server example",
    )
    print("\nLocal MCP server proof verified the unique id and Amsterdam time tool outputs.")
    print("Local MCP server example completed\n")
    print("-" * 25 + "\n")


async def public_mcp_server_example() -> None:
    # HostedMCPTools do not require manual connection
    public_server_url = os.getenv("MCP_PUBLIC_SERVER_URL")
    if not public_server_url:
        print("MCP_PUBLIC_SERVER_URL is not set; skipping hosted MCP server example.")
        print("Set MCP_PUBLIC_SERVER_URL to a public tunnel URL ending in /sse to opt in.")
        return
    public_server_url = public_server_url.rstrip("/")
    if not public_server_url.endswith("/sse"):
        raise ValueError("MCP_PUBLIC_SERVER_URL must be a public URL ending in /sse.")

    public_agent = Agent(
        name="public_MCP_Agent",
        instructions="You are a helpful assistant",
        description="Helpful assistant",
        model="gpt-5.4-mini",
        tools=[
            HostedMCPTool(  # <- public mcp server (requires ngrok)
                tool_config={
                    "type": "mcp",
                    "server_label": "mcp-tools-server",
                    # server_url must be accessible from the internet (not locally)
                    "server_url": public_server_url,
                    "require_approval": "never",
                    "headers": {"Authorization": f"Bearer {app_token}"},
                }
            ),
        ],
    )
    agency_public = Agency(public_agent)
    print("Running public MCP server example")
    print("-" * 25)
    sse_server = None
    try:
        sse_server = launch_sse_server()
        await asyncio.sleep(5)  # wait for the server to start
        response = await agency_public.get_response("Get secret word using seed 2 and then list directory")
        public_output = str(response.final_output)
        print(public_output)
        _require_text(public_output.lower(), ["strawberry"], "Hosted MCP server example")
        _require_text(public_output, ["sse_mcp_server.py"], "Hosted MCP server example")
    except Exception as e:
        print(
            f"Error using public MCP server: {e}\n Please check the ngrok url and try again.\n"
            "If issue persists, try manually starting sse server by running `python examples/utils/sse_mcp_server.py`"
        )
        raise
    finally:
        if sse_server is not None:
            _stop_sse_server(sse_server)
    print("\nHosted MCP server proof verified the secret word and utils directory listing.")
    print("Hosted MCP server example completed")
    print("-" * 25)


if __name__ == "__main__":
    print("MCP Server Example")
    print("=" * 50)
    asyncio.run(local_mcp_server_example())
    asyncio.run(public_mcp_server_example())
