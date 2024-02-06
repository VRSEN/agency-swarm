import os
from typing import Optional

from agency_swarm.tools import BaseTool
from pydantic import Field, model_validator
import importlib

from agency_swarm.util.create_agent_template import example_tool_template


class CreateTool(BaseTool):
    """
    This tool creates tools for the agent.
    """
    chain_of_thought: str = Field(
        ..., description="Think step by step to determine how to best implement this tool.", exclude=True
    )
    tool_name: str = Field(..., description="Name of the tool class in camel case.", examples=["ExampleTool"])
    tool_code: str = Field(
        ..., description="Correct code for this tool written in python. Must include all the import statements, "
                         "as well as the primary tool class that extends BaseTool. Name of this class must match tool_name.", examples=[example_tool_template]
    )

    def run(self):
        os.chdir(self.shared_state.get("agency_path"))
        os.chdir(self.shared_state.get("agent_name"))

        with open("./tools/" + self.tool_name + ".py", "w") as f:
            f.write(self.tool_code)
            f.close()

        os.chdir(self.shared_state.get("default_folder"))

        return f"Tool {self.tool_name} has been created successfully. You can now test it with TestTool."



