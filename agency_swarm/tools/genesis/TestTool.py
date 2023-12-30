import os
from typing import Optional

from agency_swarm.tools import BaseTool
from pydantic import Field, model_validator
import importlib


class TestTool(BaseTool):
    """
    This tool tests other tools defined in tools.py file with the given arguments. Make sure to define the run method before testing.
    """
    chain_of_thought: str = Field(
        ..., description="Think step by step to determine the correct arguments for testing.", exclude=True
    )
    tool_name: str = Field(..., description="Name of the tool to be run. Must be defined in tools.py file.")
    arguments: Optional[str] = Field(...,
                                     description="Arguments to be passed to the tool for testing. "
                                                 "Must be in serialized json format.")

    def run(self):
        # import tool by self.tool_name from local tools.py file
        tool = importlib.import_module('tools')

        try:
            Tool = getattr(tool, self.tool_name)
        except AttributeError:
            return f"Tool {self.tool_name} not found in tools.py file."

        try:
            tool = Tool(**eval(self.arguments))
        except Exception as e:
            return f"Error initializing tool with arguments {self.arguments}. Error: {e}"

        output = tool.run()

        if not output:
            raise ValueError(f"Tool {self.tool_name} did not return any output.")

        return "Successfully initialized and ran tool. Output: " + output

    @model_validator(mode="after")
    def validate_tool_name(self):
        # check if tools.py file exists
        if not os.path.isfile("tools.py"):
            raise ValueError(f"tools.py file does not exist. Please use ListDir tool to check the contents of the "
                             f"current folder and ChangeDri to navigate to the correct folder.")
