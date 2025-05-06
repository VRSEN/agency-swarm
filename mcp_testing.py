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
from agency_swarm.tools.mcp import MCPServerStdio, MCPServerSse
from agency_swarm.tools import BaseTool

load_dotenv()

samples_dir = os.path.join(os.path.dirname(__file__), "tests", "data", "files")

# sse_server = MCPServerSse(
#     name="SSE Python Server",
#     params={"url": "http://localhost:8080/sse", "strict": False},
#     # allowed_tools=["get_secret_word"]
# )

# youtube_server = MCPServerStdio(
#     name="Youtube Server",
#     params={
#         "command": "npx",
#         "args": ["-y", "youtube-data-mcp-server"],
#         # "strict": True,
#         "env": {
#             "YOUTUBE_API_KEY": os.getenv("YOUTUBE_API_KEY"),
#         },
#         "strict": True,
#     },
#     # strict=True,
#     cache_tools_list=True,
#     allowed_tools=["getVideoDetails"]
# )
class GetId(BaseTool):

    def run(self):
        return "aslcjkn12123"

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
        "strict": False,
    },
)
agent1 = Agent(
    name="test",
    description="test",
    instructions="Your name is John",
    # mcp_servers=[sse_server],
    temperature=0,
)
agent2 = Agent(
    name="test2",
    description="test2",
    instructions="Your name is Alan",
    # tools=[GetId],
    # mcp_servers=[filesystem_server],
    temperature=0,
)
agent3 = Agent(
    name="test3",
    description="test3",
    instructions="Your name is Bob",
    mcp_servers=[git_server],
    temperature=0,
)

test_agency = Agency([agent1, agent2, agent3,[agent1, agent2], [agent1, agent3]])




if __name__ == "__main__":
    import logging
    logging.getLogger("agency_swarm").setLevel(logging.INFO)
    logging.basicConfig(level=logging.INFO, force=True)
    # test_agency.run_demo()
    # print(test_agency.get_completion("get the files inside the available directory", recipient_agent=agent2))
    print(test_agency.get_completion("get latest commit from this repo: D:\work\VRSEN\code\agency-swarm-fork", recipient_agent=agent3))
    # test_agency.mcp_cleanup()