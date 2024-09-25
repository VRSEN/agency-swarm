from agency_swarm import Agent
from agency_swarm.agents.agent import DEFAULT_MODEL
from .tools.CreateToolsFromOpenAPISpec import CreateToolsFromOpenAPISpec


class OpenAPICreator(Agent):
    def __init__(self, model=DEFAULT_MODEL):
        super().__init__(
            description="This agent is responsible for creating new tools from an OpenAPI specifications.",
            instructions="./instructions.md",
            tools=[CreateToolsFromOpenAPISpec],
            model=model,
        )
