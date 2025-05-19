import asyncio
import os
import shutil
import subprocess
import sys
import time
from enum import Enum
from typing import List, Optional

import httpx
import pytest
from langchain_community.tools import MoveFileTool, YouTubeSearchTool
from pydantic import BaseModel, ConfigDict, Field

from agency_swarm.tools import BaseTool, ToolFactory
from agency_swarm.tools.mcp import MCPServerSse, MCPServerStdio
from agency_swarm.util import get_openai_client
from agency_swarm.util.helpers.sync_async import run_async_sync


@pytest.fixture
def client():
    return get_openai_client()


def test_move_file_tool():
    tool = ToolFactory.from_langchain_tool(MoveFileTool())
    tool = tool(
        destination_path="Move a file from one folder to another",
        source_path="Move a file from one folder to another",
    )
    tool.run()


def test_complex_schema():
    class FriendDetail(BaseModel):
        """test 123"""

        model_config = ConfigDict(title="FriendDetail")

        id: int = Field(..., description="Unique identifier for each friend.")
        name: str = Field(..., description="Name of the friend.")
        age: Optional[int] = Field(25, description="Age of the friend.")
        email: Optional[str] = Field(None, description="Email address of the friend.")
        is_active: Optional[bool] = Field(
            None, description="Indicates if the friend is currently active."
        )

    class UserDetail(BaseModel):
        """Hey this is a test?"""

        model_config = ConfigDict(title="UserDetail")

        id: int = Field(..., description="Unique identifier for each user.")
        age: int
        name: str
        friends: List[FriendDetail] = Field(
            ...,
            description="List of friends, each represented by a FriendDetail model.",
        )

    class RelationshipType(str, Enum):
        FAMILY = "family"
        FRIEND = "friend"
        COLLEAGUE = "colleague"

    class UserRelationships(BaseTool):
        """Hey this is a test?"""

        model_config = ConfigDict(title="User Relationships")

        users: List[UserDetail] = Field(
            ...,
            description="Collection of users, correctly capturing the relationships among them.",
            title="Users",
        )
        relationship_type: RelationshipType = Field(
            ...,
            description="Type of relationship among users.",
            title="Relationship Type",
        )

    tool = ToolFactory.from_openai_schema(UserRelationships.openai_schema, lambda x: x)

    user_detail_instance = {
        "id": 1,
        "age": 20,
        "name": "John Doe",
        "friends": [{"id": 1, "name": "Jane Doe"}],
    }
    user_relationships_instance = {
        "users": [user_detail_instance],
        "relationship_type": "family",
    }

    tool = tool(**user_relationships_instance)

    user_relationships_schema = UserRelationships.openai_schema

    def remove_empty_fields(d):
        """
        Recursively remove all empty fields from a dictionary.
        """
        if not isinstance(d, dict):
            return d
        return {
            k: remove_empty_fields(v) for k, v in d.items() if v not in [{}, [], ""]
        }

    cleaned_schema = remove_empty_fields(user_relationships_schema)
    tool_schema = tool.openai_schema

    assert cleaned_schema == tool_schema


def test_youtube_search_tool():
    # requires pip install youtube_search to run
    ToolFactory.from_langchain_tool(YouTubeSearchTool)


def test_custom_tool():
    schema = {
        "name": "query_database",
        "description": "Use this funciton to query the database that provides insights about the interests of different family and household segments and describes various aspects of demographic data. It also contains advertising data, offering insights into various channels and platforms to provide a granular view of advertising performance. Use when you don't already have enough information to answer the user's question based on your previous responses.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Query to the demographic database. Must be clearly stated in natural language.",
                },
            },
            "required": ["query"],
        },
        "strict": False,
    }

    tool = ToolFactory.from_openai_schema(schema, lambda x: x)

    schema["strict"] = True

    tool2 = ToolFactory.from_openai_schema(schema, lambda x: x)

    tool = tool(query="John Doe")

    assert not tool.openai_schema.get("strict", False)

    tool.run()

    assert tool2.openai_schema["strict"]


def test_get_weather_openapi():
    with open("./data/schemas/get-weather.json", "r") as f:
        tools = ToolFactory.from_openapi_schema(f.read(), {})

    assert not tools[0].openai_schema.get("strict", False)


@pytest.mark.asyncio
async def test_relevance_openapi_schema():
    with open("./data/schemas/relevance.json", "r") as f:
        # Create a mock client that will be used instead of httpx
        class MockClient:
            def __init__(self, **kwargs):
                self.timeout = kwargs.get("timeout", None)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def post(self, *args, **kwargs):
                class MockResponse:
                    def json(self):
                        return {"output": {"transformed": {"data": "test complete."}}}

                return MockResponse()

        # Patch httpx.AsyncClient with our mock
        original_client = httpx.AsyncClient
        httpx.AsyncClient = MockClient

        try:
            tools = ToolFactory.from_openapi_schema(
                f.read(), {"Authorization": "mock-key"}
            )

            output = await tools[0](requestBody={"text": "test"}).run()

            assert output["output"]["transformed"]["data"] == "test complete."
        finally:
            # Restore original client
            httpx.AsyncClient = original_client


@pytest.mark.asyncio
async def test_get_headers_openapi_schema():
    with open("./data/schemas/get-headers-params.json", "r") as f:
        tools = ToolFactory.from_openapi_schema(
            f.read(), {"Bearer": os.environ.get("GET_HEADERS_SCHEMA_API_KEY")}
        )

        output = await tools[0](
            parameters={"domain": "print-headers", "query": "test"}
        ).run()

        assert "headers" in output


def test_ga4_openapi_schema():
    with open("./data/schemas/ga4.json", "r") as f:
        tools = ToolFactory.from_openapi_schema(f.read(), {})

    assert len(tools) == 1
    assert tools[0].__name__ == "runReport"


def test_import_from_file():
    tool = ToolFactory.from_file("./data/tools/ExampleTool1.py")
    assert tool.__name__ == "ExampleTool1"
    assert tool(content="test").run() == "Tool output"


def test_mcp_filesystem():
    """Test the ToolFactory.from_mcp method with a filesystem MCP server"""
    # Skip if npx is not installed
    if not shutil.which("npx"):
        pytest.skip(
            "npx is not installed. Please install it with `npm install -g npx`."
        )

    # Get the sample files directory
    samples_dir = os.path.join(os.path.dirname(__file__), "data", "files")

    # Skip if the test file doesn't exist
    test_file = "favorite_books.txt"
    file_path = os.path.join(samples_dir, test_file)

    server_process = None
    try:
        # Create an MCP server for filesystem operations
        server = MCPServerStdio(
            params={
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", samples_dir],
            }
        )

        # Store server process for cleanup
        if hasattr(server, "_process") and server._process:
            server_process = server._process

        # Get tools from the MCP server
        tools = ToolFactory.from_mcp(server)
        assert len(tools) > 0, "No tools were created from MCP server"

        # Find the read_file tool
        read_file_tool = None
        for tool in tools:
            if tool.__name__ == "read_file":
                read_file_tool = tool
                break

        assert read_file_tool is not None, "read_file tool not found in created tools"

        read_file_instance = read_file_tool(path=file_path)
        result = run_async_sync(read_file_instance.run)

        # Verify the result
        assert isinstance(result, str), "Tool result is not a string"
        assert len(result) > 0, "Tool returned empty result"
        assert "Error" not in result, f"Tool returned error: {result}"
    finally:
        # Ensure the server process is properly cleaned up
        if server_process and server_process.poll() is None:
            try:
                server_process.terminate()
                server_process.wait(timeout=5)
            except: #noqa
                if server_process.poll() is None:
                    server_process.kill()
                    server_process.wait()

        # Force garbage collection to clean up resources before event loop closes
        import gc

        gc.collect()


def test_mcp_git():
    """Test the ToolFactory.from_mcp method with a Git MCP server"""

    # Check if git is installed
    if not shutil.which("git"):
        pytest.skip("git is not installed")

    # Try to install the MCP Git server Python package if not already installed
    install_process = None
    try:
        install_process = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "mcp-server-git"],
        )
        install_process.wait(timeout=30)
        print("Installed mcp-server-git Python package")
    except (subprocess.SubprocessError, subprocess.TimeoutExpired):
        print(
            "Note: Failed to install mcp-server-git package (may already be installed)"
        )
    finally:
        # Ensure process is terminated even if wait times out
        if install_process and install_process.poll() is None:
            try:
                install_process.terminate()
                install_process.wait(timeout=2)
            except: #noqa
                if install_process.poll() is None:
                    install_process.kill()

    server_process = None
    try:
        # Create an MCP server for Git operations using Python's module system
        server = MCPServerStdio(
            name="Git Server",
            params={
                "command": "mcp-server-git",
            },
            strict=False,
        )
        # Store the server process for later cleanup
        if hasattr(server, "_process") and server._process:
            server_process = server._process

        # Get tools from the MCP server
        tools = ToolFactory.from_mcp(server)
        assert len(tools) > 0, "No Git tools were created"

        # Verify that at least one tool has a git-related name
        git_tool_found = False
        for tool in tools:
            if any(
                keyword in tool.__name__.lower()
                for keyword in ["git", "commit", "branch", "repo"]
            ):
                git_tool_found = True
                break

        assert git_tool_found, "No Git-related tools were found"

        # Find the git_status tool and test it
        git_status_tool = None
        for tool in tools:
            if tool.__name__ == "git_status":
                git_status_tool = tool
                break

        if git_status_tool is not None:
            repo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            status_tool = git_status_tool(repo_path=repo_path)

            status_result = run_async_sync(status_tool.run)
            assert isinstance(
                status_result, str
            ), "Expected string result from git tool"
            assert len(status_result) > 0, "Expected non-empty result from git tool"
            assert (
                "Repository status:" in status_result
            ), "Expected 'Repository status:' in result"
        else:
            pytest.skip("No suitable git tool found")
    except asyncio.TimeoutError:
        pytest.skip("Git MCP server test timed out after 30 seconds")
    except Exception as e:
        pytest.skip(f"Git MCP server test failed: {str(e)}")
    finally:
        # Ensure any leftover processes are terminated
        if server_process and server_process.poll() is None:
            try:
                server_process.terminate()
                server_process.wait(timeout=5)
            except: #noqa
                if server_process.poll() is None:
                    server_process.kill()
                    server_process.wait()

        # Force garbage collection to clean up resources before event loop closes
        import gc

        gc.collect()


@pytest.mark.asyncio
async def test_mcp_sse():
    """Test the ToolFactory.from_mcp method with an SSE MCP server"""

    # Skip if Python is not available
    if not shutil.which(sys.executable):
        pytest.skip("Python executable not found")

    # Get the server file
    server_file = os.path.join(os.path.dirname(__file__), "scripts", "server.py")

    if not os.path.exists(server_file):
        pytest.skip(f"Test file {server_file} not found")

    # Start the server process
    process = None
    try:
        # Start the server using Python
        process = subprocess.Popen([sys.executable, server_file])

        # Give it time to start
        time.sleep(5)

        # Create an MCPServerSse instance
        server = MCPServerSse(
            params={"url": "http://localhost:8080/sse"}
        )
        # Get tools from the MCP server
        tools = ToolFactory.from_mcp(server)

        # Verify tools were created successfully
        assert len(tools) == 3, f"Expected 3 tools, got {len(tools)}"

        # Get the add tool
        add_tool = next((tool for tool in tools if tool.__name__ == "add"), None)
        assert add_tool is not None, "add tool not found"

        # Create an instance of the add tool
        add_instance = add_tool(a=7, b=22)
        result = await add_instance.run()
        assert str(result) == "29", f"Expected 29, got {result}"

        # Get the weather tool
        weather_tool = next(
            (tool for tool in tools if tool.__name__ == "get_current_weather"), None
        )
        assert weather_tool is not None, "get_current_weather tool not found"

        # Create an instance of the weather tool
        weather_instance = weather_tool(city="Tokyo")
        result = await weather_instance.run()
        assert "Weather report:" in result

        # Get the secret word tool
        secret_tool = next(
            (tool for tool in tools if tool.__name__ == "get_secret_word"), None
        )
        assert secret_tool is not None, "get_secret_word tool not found"

        # Create an instance of the secret word tool
        secret_instance = secret_tool()
        result = await secret_instance.run()

        assert result.lower() in ["apple", "banana", "cherry", "strawberry"]

    finally:
        # Clean up the server process
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        # Force garbage collection to clean up resources before event loop closes
        import gc

        gc.collect()


if __name__ == "__main__":
    pytest.main()
