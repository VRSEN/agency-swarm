import sys

# Ensure the agency_swarm package is found
sys.path.insert(0, "./agency-swarm")

from pydantic import BaseModel, Field

from agency_swarm import Agent
from agency_swarm.agency.agency import Agency
from agency_swarm.tools.mcp import MCPServerSse, MCPServerStdio, MCPServerStreamableHttp, MCPToolParams

# --- IMPORTANT ---
# This demo requires the example SSE and HTTP servers to be running.
# Please run the following commands in separate terminals before executing this script:
# python tests/scripts/sse_server.py
# python tests/scripts/http_server.py
# --- IMPORTANT ---

# Define the SSE MCP Server connection
sse_server = MCPServerSse(
    name="SSE_Python_Server",
    params={"url": "http://localhost:8080/sse"},
    strict=False,
)

# Example on how to use pre-loaded tools
password_tool = MCPToolParams(
    name="get_secret_password", # Name should exactly match the tool name in the server
    description="Get the secret password",
    # Target tool has no inputs - leave properties blank
    inputSchema={"type": "object", "properties": {}, "required": []}
)

# Schema can also be provided as a Pydantic model
class InputSchema(BaseModel):
    a: int = Field(..., description="First number")
    b: int = Field(..., description="Second number")

add_tool = MCPToolParams(
    name="add_numbers",
    description="Add two numbers",
    # Schema can be provided as a dictionary or a Pydantic model
    inputSchema=InputSchema
)

# Define the HTTP MCP Server connection
http_server = MCPServerStreamableHttp(
    name="HTTP_Python_Server",
    params={"url": "http://localhost:7860/mcp"},
    pre_loaded_tools=[password_tool, add_tool]
)

# Define an MCP server for filesystem access
filesystem_server = MCPServerStdio(
    name="Filesystem_Server",
    params={
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "."],
    },
    strict=False,
    # If you want to restrict agent to certain tools from the server, specify them in the allowed_tools
    allowed_tools=["list_allowed_directories", "list_directory", "read_file"]
)

# Define an agent that uses both MCP servers
mcp_agent = Agent(
    name="MCPAgent",
    description="An agent demonstrating MCP SSE and Stdio server usage.",
    instructions="You have access to an SSE server and a Filesystem server. Use the 'get_secret_word' function from the SSE_Python_Server tool OR list files using the Filesystem_Server tool.",
    mcp_servers=[sse_server, filesystem_server, http_server],
    temperature=0.1,
)

# Create the agency
agency = Agency([mcp_agent])

print("-----------------------------------------------------")
print(" Agency Swarm - MCP Demo")
print("-----------------------------------------------------")
print("This demo showcases an agent (`MCPAgent`) equipped with two MCP servers:")
print(
    "  1. SSE Server: Connects to a local SSE server to fetch a secret word or get the current weather."
)
print(
    "  2. Filesystem Server: Connects to a local filesystem server to list/read files."
)
print("-----------------------------------------------------")
print("IMPORTANT: Ensure the SSE and HTTP servers are running in a separate terminal:")
print("$ python tests/scripts/sse_server.py")
print("$ python tests/scripts/http_server.py")
print("-----------------------------------------------------")
print("Starting interactive demo session...")
print("Try asking the agent to perform tasks using its MCP tools, for example:")
print("  - 'Get the secret word'")
print("  - 'Get the secret password'")
print("  - 'Summarize the contents of the README.md file in 5 bullet points'")
print("  - 'What is the weather in Tokyo?'")
print("-----------------------------------------------------")

try:
    agency.run_demo()
except Exception as e:
    # Using logger.error for consistency after refactoring
    # Assuming logger setup exists or adding basic setup if needed
    import logging

    logger = logging.getLogger(__name__)
    if not logger.hasHandlers():  # Check if logger is already configured
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    logger.error(f"\nAn error occurred during the demo: {e}", exc_info=True)
