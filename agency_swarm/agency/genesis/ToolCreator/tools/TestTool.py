import os
from typing import Optional

from agency_swarm.tools import BaseTool, ToolFactory
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
        os.chdir(self.shared_state.get("agency_path"))
        os.chdir(self.shared_state.get("agent_name"))

        # import tool by self.tool_name from local tools.py file
        try:
            tool = ToolFactory.from_file(f"./tools/")
        except Exception as e:
            raise ValueError(f"Error importing tool {self.tool_name}: {e}")
        finally:
            os.chdir(self.shared_state.get("default_folder"))

        try:
            output = tool.run()
        except Exception as e:
            raise ValueError(f"Error running tool {self.tool_name}: {e}")
        finally:
            os.chdir(self.shared_state.get("default_folder"))

        if not output:
            raise ValueError(f"Tool {self.tool_name} did not return any output.")

        return "Successfully initialized and ran tool. Output: " + output

    @model_validator(mode="after")
    def validate_tool_name(self):
        tool_path = os.path.join(self.shared_state.get("agency_path"), self.shared_state.get("agent_name"))
        tool_path = os.path.join(str(tool_path), "tools")
        tool_path = os.path.join(tool_path, self.tool_name + ".py")

        # check if tools.py file exists
        if not os.path.isfile(tool_path):
            available_tools = os.listdir(os.path.join(self.shared_state.get("agency_path"), self.shared_state.get("agent_name")))
            available_tools = [tool for tool in available_tools if tool.endswith(".py")]
            available_tools = [tool for tool in available_tools if not tool.startswith("__") or tool.startswith(".")]
            available_tools = [tool.replace(".py", "") for tool in available_tools]
            available_tools = ", ".join(available_tools)
            raise ValueError(f"Tool {self.tool_name} not found. Available tools are: {available_tools}")

        return True
