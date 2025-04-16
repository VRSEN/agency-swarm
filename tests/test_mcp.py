import os
import sys
import time
import subprocess

import pytest

from agency_swarm.agents.agent import Agent
from agency_swarm.agency import Agency
from agency_swarm.tools.mcp import MCPServerStdio, MCPServerSse

from dotenv import load_dotenv

load_dotenv()

samples_dir = os.path.join(os.path.dirname(__file__), "data", "files")
server_file = os.path.join(os.path.dirname(__file__), "data", "files", "server.py")


@pytest.fixture(scope="module", autouse=True)
def start_server():
    # Start the server as a subprocess
    process = subprocess.Popen([sys.executable, server_file])
    time.sleep(5)  # Give it time to start
    yield
    process.terminate()
    process.wait()


@pytest.fixture(scope="module")
def agency():
    filesystem_server = MCPServerStdio(
        name="Filesystem Server",
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", samples_dir],
            "strict": False,
        }
    )

    git_server = MCPServerStdio(
        name="Git Server",
        params={
            "command": "mcp-server-git",
            "strict": False,
        }
    )

    sse_server = MCPServerSse(
        name="SSE Python Server",
        params={
            "url": "http://localhost:8080/sse",
            "strict": False
        }
    )

    agent = Agent(
        name="test",
        description="test",
        instructions="test",
        mcp_servers=[filesystem_server, git_server, sse_server],
        temperature=0
    )

    print("tools", agent.tools)

    return Agency([agent])


# Might take a bit to process
def test_read_filesystem(agency):
    result = agency.get_completion(f"read the contents of {samples_dir} folder")
    print(result)
    assert "server.py" in result


def test_read_git_commit(agency):
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    result = agency.get_completion(f"read the last commit of the {root_dir} folder")
    print(result)
    assert "Author" in result


def test_get_secret_word(agency):
    result = agency.get_completion("get secret word")
    print(result)
    assert "strawberry" in result.lower()


if __name__ == "__main__":
    import pytest
    pytest.main(["-v", __file__])


