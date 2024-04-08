from agency_swarm import Agent
from .tools.CreateToolsFromOpenAPISpec import CreateToolsFromOpenAPISpec


class OpenAPICreator(Agent):
    def __init__(self):
        super().__init__(
            description="This agent is responsible for creating new tools from an OpenAPI specifications.",
            instructions="./instructions.md",
            tools=[CreateToolsFromOpenAPISpec]
        )