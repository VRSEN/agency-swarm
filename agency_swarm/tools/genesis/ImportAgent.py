import os

from pydantic import Field, field_validator

from agency_swarm import BaseTool
from agency_swarm.tools.genesis.util import get_modules
from agency_swarm.util import create_agent_template

agent_paths = get_modules('agency_swarm.agents')
available_agents = [item.split(".")[-1] for item in agent_paths]

description = f"Name of the agent to be imported. Available agents are: " + str(available_agents)


class ImportAgent(BaseTool):
    """
    This tool imports an existing agent from agency swarm framework. Please make sure to first use the GetAvailableAgents tool to get the list of available agents.
    """
    agent_name: str = Field(...,
                            description="Name of the agent to be imported.")

    def run(self):
        # find item in available_agents dict by value
        import_path = [item for item in agent_paths if self.agent_name in item][0]

        import_path = import_path.replace(f".{self.agent_name}", "")

        # convert camel case to snake case
        instance_name = ''.join(['_'+i.lower() if i.isupper() else i for i in self.agent_name]).lstrip('_')

        create_agent_template(self.agent_name)

        os.chdir(self.agent_name)

        # add import to self.agent_name.py
        with open(f"{self.agent_name}.py", "a") as f:
            f.write(f"\nfrom {import_path} import {self.agent_name}\n")
            f.write(f"{instance_name} = {self.agent_name}()")

        return "Success. Agent has been imported. You can now use it in your agency."

    @field_validator("agent_name", mode='after')
    @classmethod
    def agent_name_exists(cls, v):
        if v not in available_agents:
            raise ValueError(
                f"Agent with name {v} does not exist. Available agents are: {available_agents}")
        return v