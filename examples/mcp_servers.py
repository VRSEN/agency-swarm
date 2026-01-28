"""
An example of running an agency with a local and a public MCP server.

This example connects to the pre-made MCP servers with custom tools
that can be found at examples/utils/stdio_mcp_server.py and examples/utils/sse_mcp_server.py

The public MCP server is running on port 8000 and can be accessed at http://localhost:8000/sse
Additionally, you can set up custom APP_TOKEN in .env file for auth, otherwise the token will be set to "test_token_123".

Run the example with: python examples/mcp_servers.py
It will ask the agent to use tools from both MCP servers and present the results.

To fully test the public MCP server example (copy/paste):
1) Start ngrok in one terminal:
ngrok http 8000

2) In another terminal (replace YOUR_NGROK_ID):
MCP_PUBLIC_SERVER_URL="https://YOUR_NGROK_ID.ngrok-free.app/sse" python examples/mcp_servers.py

IF you do not want to run the public MCP server, you can comment out the public_mcp_server_example() call in the main function below.
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
def launch_sse_server():
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


mcp_agent_local = Agent(
    name="local_MCP_Agent",
    instructions="You are a helpful assistant",
    description="Helpful assistant",
    model="gpt-5.2",
    mcp_servers=[stdio_server],  # <- local mcp server
)

agency_local = Agency(mcp_agent_local)


async def local_mcp_server_example():
    # Agent will handle execution lifecycle of the MCP server automatically.
    print("Running local MCP server example")
    print("-" * 25)
    message = "Get unique id and then current time in Europe/Amsterdam"
    print(f"Sending message: {message}")
    response = await agency_local.get_response(message)
    print(f"Answer: {response.final_output}")
    print("\nIf you see the time and id in the answer, that means agent used the local MCP server successfully")
    print("Local MCP server example completed\n")
    print("-" * 25 + "\n")


async def public_mcp_server_example():
    # HostedMCPTools do not require manual connection
    public_server_url = os.getenv("MCP_PUBLIC_SERVER_URL")
    if not public_server_url:
        print("MCP_PUBLIC_SERVER_URL is not set; skipping public MCP server example.")
        print("Set MCP_PUBLIC_SERVER_URL to your ngrok URL (including /sse) to enable it.")
        return
    public_server_url = public_server_url.rstrip("/")

    public_agent = Agent(
        name="public_MCP_Agent",
        instructions="You are a helpful assistant",
        description="Helpful assistant",
        model="gpt-5.2",
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
        response = await agency_public.get_response("Get secret word and then list directory")
        print(response.final_output)
    except Exception as e:
        print(
            f"Error using public MCP server: {e}\n Please check the ngrok url and try again.\n"
            "If issue persists, try manually starting sse server by running `python examples/utils/sse_mcp_server.py`"
        )
        return
    finally:
        if sse_server is not None:
            sse_server.terminate()
    print(
        "\nIf secret word is 'strawberry' and agent presented a list of files from the utils folder,"
        " that means the public MCP server worked successfully"
    )
    print("Public MCP server example completed")
    print("-" * 25)


if __name__ == "__main__":
    print("MCP Server Example")
    print("=" * 50)
    asyncio.run(local_mcp_server_example())
    asyncio.run(public_mcp_server_example())  # <- comment this out if you want to run local example only
