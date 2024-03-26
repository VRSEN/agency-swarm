import os
from typing import Optional

from agency_swarm.agency.genesis.util import check_agency_path, check_agent_path
from agency_swarm.tools import BaseTool
from pydantic import Field, model_validator
import importlib

from agency_swarm.util.cli.create_agent_template import example_tool_template


class CreateTool(BaseTool):
    """
    This tool creates tools for the agent.
    """
    agent_name: str = Field(
        ..., description="Name of the agent to create the tool for."
    )
    chain_of_thought: str = Field(
        ..., description="Think step by step to determine how to best implement this tool.", exclude=True
    )
    tool_name: str = Field(..., description="Name of the tool class in camel case.", examples=["ExampleTool"])
    tool_code: str = Field(
        ..., description="Correct code for this tool written in python. Must include all the import statements, "
                         "as well as the primary tool class that extends BaseTool. Name of this class must match tool_name.",
        examples=[example_tool_template]
    )
    agency_name: str = Field(
        None, description="Name of the agency to create the tool for. Defaults to the agency currently being created."
    )

    def run(self):
        os.chdir(self.shared_state.get("agency_path"))
        os.chdir(self.agent_name)

        with open("./tools/" + self.tool_name + ".py", "w") as f:
            f.write(self.tool_code)
            f.close()

        os.chdir(self.shared_state.get("default_folder"))

        return f"Tool {self.tool_name} has been created successfully for {self.shared_state.get('agent_name')} agent. You can now test it with TestTool function."

    @model_validator(mode="after")
    def validate(self):
        if 'placeholder' in self.tool_code.lower():
            placeholder_lines = [i for i in self.tool_code.split("\n") if 'placeholder' in i.lower()]
            raise ValueError("Please replace all placeholders with the actual fully functional code for the tool."
                             f"Placeholders found: {placeholder_lines}")

        check_agency_path(self)

        check_agent_path(self)


