import os.path

from agency_swarm import BaseTool
from agency_swarm.tools.genesis.util import get_modules
import importlib

class GetAvailableAgents(BaseTool):
    """
    This tool gets the list of pre-made available agents in the framework.
    """
    def run(self):
        agent_paths = get_modules('agency_swarm.agents')
        available_agents = [item.split(".")[-1] for item in agent_paths]

        print("Available agents:")
        for agent in available_agents:
            print(agent)

        agents_and_descriptions = {}
        for path in agent_paths:
            module = importlib.import_module(path)

            class_name = path.split(".")[-1]

            cls = getattr(module, class_name)()

            agents_and_descriptions[class_name] = cls.description

        return str(agents_and_descriptions)


if __name__ == "__main__":
    tool = GetAvailableAgents(agent_name="BrowsingAgent")
    print(tool.run())