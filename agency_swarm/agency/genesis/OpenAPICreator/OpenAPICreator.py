from agency_swarm import Agent
from agency_swarm.tools import Retrieval
from .tools.CreateToolsFromOpenAPISpec import CreateToolsFromOpenAPISpec


class OpenAPICreator(Agent):

    def __init__(self, **kwargs):
        # Initialize tools in kwargs if not present
        if 'tools' not in kwargs:
            kwargs['tools'] = []

        kwargs['description'] = "This agent is responsible for creating new tools from an OpenAPI specifications."

        # Add required tools
        kwargs['tools'].extend([Retrieval, CreateToolsFromOpenAPISpec])

        # Set instructions
        kwargs['instructions'] = "./instructions.md"

        # Initialize the parent class
        super().__init__(**kwargs)