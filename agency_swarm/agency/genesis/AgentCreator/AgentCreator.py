from agency_swarm import Agent

from .tools.CreateAgentTemplate import CreateAgentTemplate
from .tools.ImportAgent import ImportAgent
from .tools.ReadManifesto import ReadManifesto


class AgentCreator(Agent):
    def __init__(self):
        super().__init__(
            description="This agent is responsible for creating new agents for the agency.",
            instructions="./instructions.md",
            tools=[ReadManifesto, ImportAgent, CreateAgentTemplate],
            temperature=None,
            model="o3-mini",
        )
