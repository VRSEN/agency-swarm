"""
An example of running an agency with a local and a public mcp server.

This example connects to the pre-made mcp servers with custom tools
that can be found at examples/utils/stdio_mcp_server.py and examples/utils/sse_mcp_server.py

The public mcp server is running on port 8000 and can be accessed at http://localhost:8000/sse/
You'll need to use ngrok to expose the server to the internet prior to running this example.
Use the following command to start ngrok:
ngrok http http://localhost:8000

Then update the server_url in the tool_config to the ngrok url.
Additionally, you can set up custom APP_TOKEN in .env file for auth, otherwise the token will be set to "test_token_123".
"""

import asyncio
import os
import subprocess
import time

from agents import HostedMCPTool
from agents.mcp.server import MCPServerStdio, MCPServerStdioParams

from agency_swarm import Agency, Agent

stdio_server = MCPServerStdio(
    MCPServerStdioParams(command="python", args=["./examples/utils/stdio_mcp_server.py"]), cache_tools_list=True
)


# Launch the SSE MCP server
def launch_sse_server():
    """Launch the SSE MCP server in a separate process"""
    env = os.environ.copy()
    env["APP_TOKEN"] = os.getenv("APP_TOKEN", "test_token_123")

    process = subprocess.Popen(
        ["python", "./examples/utils/sse_mcp_server.py"], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )

    # Give the server time to start
    time.sleep(2)
    return process


sse_server = launch_sse_server()

mcp_agent_local = Agent(
    name="local_MCP_Agent",
    instructions="You are a helpful assistant",
    description="Helpful assistant",
    model="gpt-4.1",
    mcp_servers=[stdio_server],  # <- local mcp server
)

agency_local = Agency(mcp_agent_local)

mcp_agent_public = Agent(
    name="public_MCP_Agent",
    instructions="You are a helpful assistant",
    description="Helpful assistant",
    model="gpt-4.1",
    tools=[
        HostedMCPTool(  # <- public mcp server (requires ngrok)
            tool_config={
                "type": "mcp",
                "server_label": "mcp-tools-server",
                # server_url must be accessible from the internet (not locally)
                "server_url": "https://93b404880afc.ngrok-free.app/sse/",  # <- update this with your ngrok url
                "require_approval": "never",
                "headers": {"Authorization": f"Bearer {os.getenv('APP_TOKEN', 'test_token_123')}"},
            }
        ),
    ],
)

agency_public = Agency(mcp_agent_public)


async def local_mcp_server_example():
    # Let the Agent's execution lifecycle manage MCP server connect/cleanup.
    # Do not call connect()/cleanup() manually here.
    response = await agency_local.get_response("Get unique id and then current time in Europe/Amsterdam")
    print(response.final_output)


async def public_mcp_server_example():
    # HostedMCPTools do not require manual connection
    response = await agency_public.get_response("Get secret word and then list directory")
    print(response.final_output)
    sse_server.terminate()


if __name__ == "__main__":
    asyncio.run(local_mcp_server_example())
    # asyncio.run(public_mcp_server_example())  # <- comment this out if you want to run local example only
