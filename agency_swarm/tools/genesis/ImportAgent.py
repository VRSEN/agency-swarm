from pydantic import Field, field_validator

from agency_swarm import BaseTool
from agency_swarm.tools.genesis.util import get_modules

agent_paths = get_modules('agency_swarm.agents')
available_agents = [item.split(".")[-1] for item in agent_paths]

description = f"Name of the agent to be imported. Available agents are: " + str(available_agents)


class ImportAgent(BaseTool):
    """
    This tool imports an existing agent from agency swarm framework. Prefer to use this tool if there is an available agent in the framework that might be suitable for the task.
    """
    agent_name: str = Field(...,
                            description=description)

    def run(self):
        # find item in available_agents dict by value
        import_path = [item for item in agent_paths if self.agent_name in item][0]

        import_path = import_path.replace(f".{self.agent_name}", "")

        # convert camel case to snake case
        instance_name = ''.join(['_'+i.lower() if i.isupper() else i for i in self.agent_name]).lstrip('_')

        return "To import the agent, please add the following code: \n\n" + \
            f"from {import_path} import {self.agent_name}\n" + \
            f"{instance_name} = {self.agent_name}()"

    @field_validator("agent_name", mode='after')
    @classmethod
    def agent_name_exists(cls, v):
        if v not in available_agents:
            raise ValueError(
                f"Agent with name {v} does not exist. Available agents are: {available_agents}")
        return v

if __name__ == "__main__":
    tool = ImportAgent(agent_name="BrowsingAgent")
    print(tool.run())