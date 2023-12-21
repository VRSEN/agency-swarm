import unittest, json

import sys
from typing import List

from instructor import OpenAISchema
from pydantic import Field

from agency_swarm import Agency, Agent
from agency_swarm.util.schema import dereference_schema, reference_schema
from tests.test_agent import TestAgent

sys.path.insert(0, '../agency-swarm')
from agency_swarm.tools import ToolFactory
from langchain.tools import MoveFileTool, YouTubeSearchTool, DuckDuckGoSearchRun

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
        class UserDetail(OpenAISchema):
            id: int = Field(..., description="Unique identifier for each user.")
            age: int
            name: str
            friends: List[int] = Field(...,
                                       description="Correct and complete list of friend IDs, representing relationships between users.")

        class UserRelationships(OpenAISchema):
            users: List[UserDetail] = Field(...,
                                            description="Collection of users, correctly capturing the relationships among them.")

        deref_schema = dereference_schema(UserRelationships.openai_schema)

        print("deref", json.dumps(deref_schema, indent=4))

        print("ref", json.dumps(reference_schema(deref_schema), indent=4))

        tool = ToolFactory.from_openai_schema(dereference_schema(UserRelationships.openai_schema), lambda x: x)

        print(json.dumps(tool.openai_schema, indent=4))

        tool = tool(users=[UserDetail(id=1, age=20, name="John Doe", friends=[2, 3, 4]).model_dump()])

    def test_youtube_search_tool(self):
        # requires pip install youtube_search
        tool = ToolFactory.from_langchain_tool(YouTubeSearchTool)

        self.agent = Agent(
            name="test_agent",
            tools=[tool]
        )

        agency = Agency(
            [self.agent]
        )

        message = agency.get_completion("Search YouTube for a video about lex fridman", False)

        print(message)

        self.assertTrue(message)

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
        }

        tool = ToolFactory.from_openai_schema(schema, lambda x: x)

        print(json.dumps(tool.openai_schema, indent=4))

        tool = tool(query="John Doe")

        print(tool.model_dump())

        tool.run()


if __name__ == '__main__':
    unittest.main()
