import importlib
import os
import re
from pathlib import Path

from pydantic import Field, field_validator

from agency_swarm import BaseTool
from agency_swarm.util.cli import import_agent, list_available_agents


def extract_description_from_file(file_path):
    """
    Extracts the agent's description from its Python file.
    """
    description_pattern = re.compile(
        r'\s*description\s*=\s*["\'](.*?)["\'],', re.DOTALL)
    with open(file_path, 'r', encoding='utf-8') as file:
        content = file.read()
    match = description_pattern.search(content)
    if match:
        description = ' '.join(match.group(1).split())
        return description
    return "Description not found."


def get_agent_descriptions():
    descriptions = {}

    # Dynamically get the path of the agency_swarm.agents module
    spec = importlib.util.find_spec("agency_swarm.agents")
    if spec is None or spec.origin is None:
        raise ImportError("Could not locate 'agency_swarm.agents' module.")
    agents_path = Path(spec.origin).parent

    agents = list_available_agents()
    for agent_name in agents:
        agent_file_path = agents_path / agent_name / f"{agent_name}.py"

        # Check if the agent file exists before trying to extract the description
        if agent_file_path.exists():
            descriptions[agent_name] = extract_description_from_file(agent_file_path)
        else:
            print(f"Could not find the file for agent '{agent_name}'.")

    agent_descriptions = "Available agents:\n\n"
    for name, desc in descriptions.items():
        agent_descriptions += f"'{name}': {desc}\n"

    return agent_descriptions


class ImportAgent(BaseTool):
    """
    This tool imports an existing agent from agency swarm framework. Please make sure to first use the GetAvailableAgents tool to get the list of available agents.
    """
    agent_name: str = Field(...,
                            description=get_agent_descriptions())
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

        return "Success. Agent has been imported. You can now use it in your agency."

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
