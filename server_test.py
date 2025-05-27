import os
import signal
import platform
import subprocess
import sys
import time

import pytest
from dotenv import load_dotenv

from agency_swarm.agency import Agency
from agency_swarm.agents.agent import Agent
from agency_swarm.tools.mcp import MCPServerSse, MCPServerStdio
from agency_swarm.integrations.fastapi import run_fastapi


load_dotenv()

samples_dir = os.path.join(os.path.dirname(__file__), "tests", "data", "files")
server_file = os.path.join(os.path.dirname(__file__), "tests", "scripts", "server.py")
print(samples_dir)


def start_server():
    # Start the server as a subprocess
    process = subprocess.Popen([sys.executable, server_file])
    time.sleep(5)  # Give it time to start
    yield
    # Try sending SIGINT (Ctrl+C) for a cleaner shutdown
    if platform.system() == "Windows":
        process.terminate()
    else:
        process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=10)  # Wait up to 10 seconds
    except subprocess.TimeoutExpired:
        print("Server did not terminate gracefully, sending SIGTERM")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("Server did not terminate after SIGTERM, sending SIGKILL")
            process.kill()
            process.wait()

# filesystem_server = MCPServerStdio(
#     name="Filesystem Server",
#     params={
#         "command": "npx",
#         "args": ["-y", "@modelcontextprotocol/server-filesystem", samples_dir],
#     },
# )

git_server = MCPServerStdio(
    name="Git Server",
    params={
        "command": "mcp-server-git",
    },
)

# sse_server = MCPServerSse(
#     name="SSE Python Server",
#     params={"url": "http://localhost:8080/sse", "timeout": 5},
#     strict=True,
#     allowed_tools=["get_secret_word"]
# )

# Serialize agent initialization
agents = []
for name, server in [
    ("test1", None),
    ("test2", git_server),
    ("test3", None),
]:
    if server is not None:
        agent = Agent(
            name=name,
            description="test",
            instructions="test",
            mcp_servers=[server],
            temperature=0,
        )
    else:
        agent = Agent(
            name=name,
            description="test",
            instructions="test",
            temperature=0,
        )
    agents.append(agent)

agency_1 = Agency([agents[0], [agents[0], agents[1]], [agents[0], agents[2]]], name="test1")
agents = []
for name, server in [
    # ("test1", git_server),
    ("test22", 1),
    # ("test3", 3),
]:
    agent = Agent(
        name=name,
        description="test",
        instructions="test",
        # mcp_servers=[server],
        temperature=0,
    )
    agents.append(agent)
agency_2 = Agency(agents, name="test2")

from agency_swarm.tools import BaseTool
from pydantic import Field
import os

class ExampleTool(BaseTool):
    """
    A brief description of what the custom tool does.
    The docstring should clearly explain the tool's purpose and functionality.
    It will be used by the agent to determine when to use this tool.
    """

    # Define the fields with descriptions using Pydantic Field
    example_field: str = Field(
        ..., description="Description of the example field, explaining its purpose and usage for the Agent."
    )

    def run(self):
        """
        The implementation of the run method, where the tool's main functionality is executed.
        This method should utilize the fields defined above to perform the task.
        Docstring is not required for this method and will not be used by the agent.
        """
        # Your custom tool logic goes here
        # do_something(self.example_field, api_key, account_id)

        # Return the result of the tool's operation as a string
        return "Result of ExampleTool operation"



# Might take a bit to process
def test_read_filesystem(agency):
    print("Starting test_read_filesystem")
    result = agency.get_completion(f"Use the list_directory tool to read the contents of {samples_dir} folder.", recipient_agent=agency.agents[0])
    print(result)


def test_read_git_commit(agency):
    print("Starting test_read_git_commit")
    root_dir = "D:/work/VRSEN/code/agency-swarm-fork/"
    result = agency.get_completion(f"Read the last commit of the {root_dir} folder. Provide result in the exact same format as you receive it.", recipient_agent=agency.agents[1])
    print(result)


def test_get_secret_word(agency):
    print("Starting test_get_secret_word")
    result = agency.get_completion("Get secret word using get_secret_word tool.", recipient_agent=agency.agents[2])
    print(result)

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    # start_server()
    # agency_1.demo_gradio()
    # run_fastapi(agencies=[agency_1, agency_2], port=7860, tools=[ExampleTool])
    agency_1.run_fastapi(port=7860)
