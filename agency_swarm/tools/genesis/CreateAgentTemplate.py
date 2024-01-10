import os
from typing import List

from pydantic import Field, model_validator, field_validator

from agency_swarm import BaseTool
from agency_swarm.util import create_agent_template


class CreateAgentTemplate(BaseTool):
    """
    This tool creates a template folder for a new agent that includes boilerplage code and instructions.
    """
    allowed_tools: List = ["CodeInterpreter"]  # , "Retrieval"}

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
                        f"CodeInterpreter allows the agent to execute python code in a remote environment.",
        example=["CodeInterpreter"],
    )

    def run(self):
        create_agent_template(self.agent_name,
                              self.agent_description,
                              instructions=self.instructions,
                              code_interpreter=True if "CodeInterpreter" in self.default_tools else None)

        # add agent to agency.py
        with open("agency.py", "a") as f:
            f.write(f"from .{self.agent_name} import {self.agent_name}\n")

        return f"Agent template has been created in {self.agent_name} folder."

    @model_validator(mode="after")
    def validate_tools(self):
        for tool in self.default_tools:
            if tool not in self.allowed_tools:
                raise ValueError(f"Tool {tool} is not allowed. Allowed tools are: {self.allowed_tools}")

    @field_validator("agent_name", mode='after')
    @classmethod
    def agent_name_exists(cls, v):
        if " " in v:
            raise ValueError("Agent name cannot contain spaces.")
        if not v.isalnum():
            raise ValueError("Agent name cannot contain special characters.")
        if os.path.exists("./" + v):
            raise ValueError(f"Agent with name {v} already exists.")
        return v
