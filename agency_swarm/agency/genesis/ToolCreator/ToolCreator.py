from agency_swarm import Agent
from .tools.TestTool import TestTool
from .tools.CreateTool import CreateTool


class ToolCreator(Agent):
    def __init__(self, **kwargs):
        # Initialize tools in kwargs if not present
        if 'tools' not in kwargs:
            kwargs['tools'] = []

        # Add required tools
        kwargs['tools'].extend([CreateTool, TestTool])

        # Set instructions
        if 'instructions' not in kwargs:
            kwargs['instructions'] = "./instructions.md"

        # Initialize the parent class
        super().__init__(**kwargs)


