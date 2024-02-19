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
    def validate_agent_name(self):
        if not self.shared_state.get("agency_path") and not self.agency_name:
            available_agencies = os.listdir("./")
            # filter out non-directories
            available_agencies = [agency for agency in available_agencies if os.path.isdir(agency)]
            raise ValueError(f"Please specify an agency. Available agencies are: {available_agencies}")
        elif not self.shared_state.get("agency_path") and self.agency_name:
            self.shared_state.set("agency_path", os.path.join("./", self.agency_name))

        agent_path = os.path.join(self.shared_state.get("agency_path"), self.agent_name)
        if not os.path.exists(agent_path):
            available_agents = os.listdir(self.shared_state.get("agency_path"))
            available_agents = [agent for agent in available_agents if
                                os.path.isdir(os.path.join(self.shared_state.get("agency_path"), agent))]
            raise ValueError(f"Agent {self.agent_name} not found. Available agents are: {available_agents}")
