from agency_swarm import Agent
from .tools.CreateAgentTemplate import CreateAgentTemplate
# from .tools.GetAvailableAgents import GetAvailableAgents
# from .tools.ImportAgent import ImportAgent
from .tools.ReadManifesto import ReadManifesto


class AgentCreator(Agent):

    def __init__(self, **kwargs):
        # Initialize tools in kwargs if not present
        if 'tools' not in kwargs:
            kwargs['tools'] = []

        kwargs['description'] = "This agent is responsible for creating new agents for the agency."

        # Add required tools
        kwargs['tools'].extend([CreateAgentTemplate,
                                # GetAvailableAgents,
                                ReadManifesto,
                                # ImportAgent
                                ])

        # Set instructions
        if 'instructions' not in kwargs:
            kwargs['instructions'] = "./instructions.md"

        # Initialize the parent class
        super().__init__(**kwargs)


