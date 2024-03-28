import os

from pydantic import Field, field_validator

from agency_swarm import BaseTool
from agency_swarm.util.cli import import_agent
from agency_swarm.util.helpers import get_available_agent_descriptions, list_available_agents


class ImportAgent(BaseTool):
    """
    This tool imports an existing agent from agency swarm framework. Please make sure to first use the GetAvailableAgents tool to get the list of available agents.
    """
    agent_name: str = Field(...,
                            description=get_available_agent_descriptions())
    agency_path: str = Field(
        None, description="Path to the agency where the agent will be imported. Default is the current agency.")

    def run(self):
        if not self.shared_state.get("default_folder"):
            self.shared_state.set("default_folder", os.getcwd())

        if not self.shared_state.get("agency_path") and not self.agency_path:
            return "Error: You must set the agency_path."

        if self.shared_state.get("agency_path"):
            os.chdir(self.shared_state.get("agency_path"))
        else:
            os.chdir(self.agency_path)

        import_agent(self.agent_name, "./")

        # add agent on second line to agency.py
        with open("agency.py", "r") as f:
            lines = f.readlines()
            lines.insert(1, f"from {self.agent_name} import {self.agent_name}\n")

        with open("agency.py", "w") as f:
            f.writelines(lines)

        os.chdir(self.shared_state.get("default_folder"))

        return (f"Success. {self.agent_name} has been imported. "
                f"You can now tell the user to user proceed with next agents.")

    @field_validator("agent_name", mode='after')
    @classmethod
    def agent_name_exists(cls, v):
        available_agents = list_available_agents()
        if v not in available_agents:
            raise ValueError(
                f"Agent with name {v} does not exist. Available agents are: {available_agents}")
        return v

if __name__ == "__main__":
    tool = ImportAgent(agent_name="Devid")
    tool.shared_state.set("agency_path", "./")
    tool.run()
