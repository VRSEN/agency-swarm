import os
from enum import Enum
from typing import List, Optional

import httpx
import pytest
from langchain_community.tools import MoveFileTool, YouTubeSearchTool
from pydantic import BaseModel, ConfigDict, Field

from agency_swarm.tools import BaseTool, ToolFactory
from agency_swarm.util import get_openai_client


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


if __name__ == "__main__":
    pytest.main()
