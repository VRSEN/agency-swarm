"""
An example of running an agency with a local and a public MCP server.

This example connects to the pre-made MCP servers with custom tools
that can be found at examples/utils/stdio_mcp_server.py and examples/utils/sse_mcp_server.py

The public MCP server is running on port 8000 and can be accessed at http://localhost:8000/sse/
You'll need to use ngrok to expose the server to the internet prior to running this example.
Use the following command to start ngrok:
ngrok http http://localhost:8000

Then update the server_url in the tool_config to the ngrok url.
Additionally, you can set up custom APP_TOKEN in .env file for auth, otherwise the token will be set to "test_token_123".

Run the example with: python examples/mcp_server_example.py
It will ask the agent to use tools from both MCP servers and present the results.

IF you do not want to run the public MCP server, you can comment out the public_mcp_server_example() call in the main function below.
"""

import asyncio
import os
import subprocess
import time

from agents.mcp.server import MCPServerStdio, MCPServerStdioParams
from dotenv import load_dotenv

from agency_swarm import Agency, Agent, HostedMCPTool

load_dotenv()

stdio_server = MCPServerStdio(
    MCPServerStdioParams(command="python", args=["./examples/utils/stdio_mcp_server.py"]), cache_tools_list=True
)

app_token = os.getenv("APP_TOKEN", "test_token_123")
if not app_token:
    print("APP_TOKEN not set, using default token")
    os.environ["APP_TOKEN"] = "test_token_123"


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
                "server_url": "https://8ea519b4b5ec.ngrok-free.app/sse/",  # <- update this with your ngrok url, don't forget to add /sse/ at the end
                "require_approval": "never",
                "headers": {"Authorization": f"Bearer {os.getenv('APP_TOKEN', 'test_token_123')}"},
            }
        ),
    ],
)

agency_public = Agency(mcp_agent_public)


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
    print("Running public MCP server example")
    print("-" * 25)
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
