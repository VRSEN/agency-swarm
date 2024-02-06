import os
import shutil
from typing import List

from pydantic import Field, model_validator, field_validator

from agency_swarm import BaseTool
from agency_swarm.util import create_agent_template

allowed_tools: List = ["CodeInterpreter"]

class CreateAgentTemplate(BaseTool):
    """
    This tool creates a template folder for a new agent that includes boilerplage code and instructions.
    """
    agent_name: str = Field(
        ..., description="Name of the agent to be created. Cannot include special characters or spaces."
    )
    agent_description: str = Field(
        ..., description="Description of the agent to be created."
    )
    instructions: str = Field(
        ..., description="Instructions for the agent to be created in markdown format."
    )
    default_tools: List[str] = Field(
        [], description=f"List of default tools to be included in the agent. Possible values are {allowed_tools}."
                        f"CodeInterpreter allows the agent to execute python code in a remote python environment.",
        example=["CodeInterpreter"],
    )

    def run(self):
        self.shared_state.set("agent_name", self.agent_name)

        os.chdir(self.shared_state.get("agency_path"))

        # remove folder if it already exists
        if os.path.exists(self.agent_name):
            shutil.rmtree(self.agent_name)

        create_agent_template(self.agent_name,
                              self.agent_description,
                              instructions=self.instructions,
                              code_interpreter=True if "CodeInterpreter" in self.default_tools else None,
                              include_example_tool=False)

        # add agent on second line to agency.py
        with open("agency.py", "r") as f:
            lines = f.readlines()
            lines.insert(1, f"from {self.agent_name} import {self.agent_name}\n")

        with open("agency.py", "w") as f:
            f.writelines(lines)

        os.chdir(self.shared_state.get("default_folder"))

        if "ceo" in self.agent_name.lower():
            return f"You can tell the user that the process of creating {self.agent_name} has been completed, because CEO agent does not need to utilizie any tools or APIs."

        return f"Agent template has been created for {self.agent_name}. Please now tell ToolCreator to create tools for this agent or OpenAPICreator to create API schemas, if this agent needs to utilize any tools or APIs. If this is unclear, please ask the user for more information."

    @model_validator(mode="after")
    def validate_tools(self):
        for tool in self.default_tools:
            if tool not in self.allowed_tools:
                raise ValueError(f"Tool {tool} is not allowed. Allowed tools are: {self.allowed_tools}")
