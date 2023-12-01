import unittest, json

import sys

sys.path.insert(0, '../agency-swarm')
from agency_swarm.tools import ToolFactory
from langchain.tools import MoveFileTool, YouTubeSearchTool


class ToolFactoryTest(unittest.TestCase):
    def test_movie_file_tool(self):
        tool = ToolFactory.from_langchain_tool(MoveFileTool())
        print(json.dumps(tool.openai_schema, indent=4))
        print(tool)

        tool = tool(destination_path="Move a file from one folder to another",
                    source_path="Move a file from one folder to another")

        print(tool.model_dump())

        tool.run()

    def test_youtube_search_tool(self):
        tool = ToolFactory.from_langchain_tool(YouTubeSearchTool())
        print(json.dumps(tool.openai_schema, indent=4))
        print(tool)

        tool = tool(__arg1='lex fridman podcast')

        print(tool.model_dump())

        tool.run()


if __name__ == '__main__':
    unittest.main()
