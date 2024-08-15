import asyncio
from enum import Enum
import json
import os
import sys
import unittest
from typing import List, Optional

from pydantic import Field, BaseModel

sys.path.insert(0, '../agency-swarm')
from agency_swarm.tools import ToolFactory, BaseTool
from agency_swarm.util.schema import dereference_schema, reference_schema
from langchain.tools import MoveFileTool, YouTubeSearchTool

from agency_swarm.util import get_openai_client


class ToolFactoryTest(unittest.TestCase):
    def setUp(self):
        self.client = get_openai_client()

    def test_move_file_tool(self):
        tool = ToolFactory.from_langchain_tool(MoveFileTool())
        print(json.dumps(tool.openai_schema, indent=4))
        print(tool)

        tool = tool(destination_path="Move a file from one folder to another",
                    source_path="Move a file from one folder to another")

        print(tool.model_dump())

        tool.run()

    def test_complex_schema(self):
        class FriendDetail(BaseModel):
            "test 123"
            id: int = Field(..., description="Unique identifier for each friend.")
            name: str = Field(..., description="Name of the friend.")
            age: Optional[int] = Field(25, description="Age of the friend.")
            email: Optional[str] = Field(None, description="Email address of the friend.")
            is_active: Optional[bool] = Field(None, description="Indicates if the friend is currently active.")

        class UserDetail(BaseModel):
            """Hey this is a test?"""
            id: int = Field(..., description="Unique identifier for each user.")
            age: int
            name: str
            friends: List[FriendDetail] = Field(...,
                                                description="List of friends, each represented by a FriendDetail model.")

        class RelationshipType(Enum):
            FAMILY = "family"
            FRIEND = "friend"
            COLLEAGUE = "colleague"

        class UserRelationships(BaseTool):
            """Hey this is a test?"""
            users: List[UserDetail] = Field(...,
                                            description="Collection of users, correctly capturing the relationships among them.", title="Users")
            relationship_type: RelationshipType = Field(..., description="Type of relationship among users.", title="Relationship Type")

        print("schema", json.dumps(UserRelationships.openai_schema, indent=4))

        # print("ref", json.dumps(reference_schema(deref_schema), indent=4))

        tool = ToolFactory.from_openai_schema(UserRelationships.openai_schema, lambda x: x)

        print(json.dumps(tool.openai_schema, indent=4))
        user_detail_instance = {
            "id": 1,
            "age": 20,
            "name": "John Doe",
            "friends": [
                {
                    "id": 1,
                    "name": "Jane Doe"
                }
            ]
        }
        user_relationships_instance = {
            "users": [user_detail_instance],
            "relationship_type": "family"
        }
        
        #print user detail instance
        tool = tool(**user_relationships_instance)

        user_relationships_schema = UserRelationships.openai_schema

        def remove_empty_fields(d):
            """
            Recursively remove all empty fields from a dictionary.
            """
            if not isinstance(d, dict):
                return d
            return {k: remove_empty_fields(v) for k, v in d.items() if v not in [{}, [], '']}

        cleaned_schema = remove_empty_fields(user_relationships_schema)

        print("clean schema", json.dumps(cleaned_schema, indent=4))

        print("tool schema", json.dumps(tool.openai_schema, indent=4))

        tool_schema = tool.openai_schema

        assert cleaned_schema == tool_schema

    def test_youtube_search_tool(self):
        # requires pip install youtube_search to run
        ToolFactory.from_langchain_tool(YouTubeSearchTool)

    def test_custom_tool(self):
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
            "strict": False
        }

        tool = ToolFactory.from_openai_schema(schema, lambda x: x)

        schema['strict'] = True

        tool2 = ToolFactory.from_openai_schema(schema, lambda x: x)

        print(json.dumps(tool.openai_schema, indent=4))

        tool = tool(query="John Doe")

        print(tool.model_dump())

        self.assertFalse(tool.openai_schema.get("strict", False))

        tool.run()

        self.assertTrue(tool2.openai_schema["strict"])

    def test_get_weather_openapi(self):
        with open("./data/schemas/get-weather.json", "r") as f:
            tools = ToolFactory.from_openapi_schema(f.read())

        self.assertFalse(tools[0].openai_schema.get("strict", False))

        print(json.dumps(tools[0].openai_schema, indent=4))

    def test_relevance_openapi_schema(self):
        with open("./data/schemas/relevance.json", "r") as f:
            tools = ToolFactory.from_openapi_schema(f.read(), {
                "Authorization": os.environ.get("TEST_SCHEMA_API_KEY")
            })

        print(json.dumps(tools[0].openai_schema, indent=4))

        async def gather_output():
            output = await tools[0](requestBody={"text": 'test'}).run()
            return output

        output = asyncio.run(gather_output())

        print(output)

        assert output['output']['transformed']['data'] == 'test complete.'

    def test_get_headers_openapi_schema(self):
        with open("./data/schemas/get-headers-params.json", "r") as f:
            tools = ToolFactory.from_openapi_schema(f.read(),{
                "Bearer": os.environ.get("GET_HEADERS_SCHEMA_API_KEY")
            })

        async def gather_output():
            output = await tools[0](parameters={"domain": "print-headers", "query": "test"}).run()
            return output

        output = asyncio.run(gather_output())

        self.assertTrue("headers" in output)

        print(output)

    def test_ga4_openapi_schema(self):
        with open("./data/schemas/ga4.json", "r") as f:
            tools = ToolFactory.from_openapi_schema(f.read(), {})

        print(json.dumps(tools[0].openai_schema, indent=4))

    def test_import_from_file(self):
        tool = ToolFactory.from_file("./data/tools/ExampleTool1.py")

        print(tool)

        self.assertTrue(tool.__name__ == "ExampleTool1")

        self.assertTrue(tool(content='test').run() == "Tool output")

    # def test_openapi_schema(self):
    #     with open("./data/schemas/get-headers-params.json", "r") as f:
    #         tools = ToolFactory.from_openapi_schema(f.read())

    #     schema = ToolFactory.get_openapi_schema(tools, "123")

    #     self.assertTrue(schema)




if __name__ == '__main__':
    unittest.main()
