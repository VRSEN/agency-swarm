from agency_swarm import Agent
from agency_swarm.tools import Retrieval
from agency_swarm.tools.coding import ListDir
from agency_swarm.tools.openapi import CreateToolsFromOpenAPISpec


class OpenAPICreator(Agent):

    def __init__(self, **kwargs):
        # Initialize tools in kwargs if not present
        if 'tools' not in kwargs:
            kwargs['tools'] = []
        # Add required tools
        kwargs['tools'].extend([Retrieval, CreateToolsFromOpenAPISpec, ListDir])

        # Set instructions
        kwargs['instructions'] = "./instructions.md"

        # Initialize the parent class
        super().__init__(**kwargs)