from pydantic import Field, field_validator

from agency_swarm import BaseTool
from agency_swarm.util.imports import get_class_names_from_submodules

available_agents = get_class_names_from_submodules('agency_swarm.agents')

description = f"Name of the agent to be imported. Available agents are:" + str(
    [item for sublist in available_agents.values() for item in sublist])


class ImportAgent(BaseTool):
    """
    This tool imports an existing agent from agency swarm framework.
    """
    agent_name: str = Field(...,
                            description=description)

    def run(self):
        # find item in available_agents dict by value
        import_path = [k for k, v in available_agents.items() if self.agent_name in v][0]

        import_path = import_path.replace(f".{self.agent_name}", "")

        return "To import the agent, please add the following code: \n\n" + \
            f"from {import_path} import {self.agent_name}\n" + \
            f"agent = {self.agent_name}()"

    @field_validator("agent_name", mode='after')
    @classmethod
    def agent_name_exists(cls, v):
        if v not in [item for sublist in available_agents.values() for item in sublist]:
            raise ValueError(
                f"Agent with name {v} does not exist. Available agents are: {[item for sublist in available_agents.values() for item in sublist]}")
        return v
