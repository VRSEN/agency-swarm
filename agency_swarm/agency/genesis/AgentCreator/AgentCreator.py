from agency_swarm import Agent
from .tools.ImportAgent import ImportAgent
from .tools.CreateAgentTemplate import CreateAgentTemplate
from .tools.ReadManifesto import ReadManifesto

class AgentCreator(Agent):
    def __init__(self):
        super().__init__(
            description="This agent is responsible for creating new agents for the agency.",
            instructions="./instructions.md",
            tools=[ImportAgent, CreateAgentTemplate, ReadManifesto],
            temperature=0.3,
        )