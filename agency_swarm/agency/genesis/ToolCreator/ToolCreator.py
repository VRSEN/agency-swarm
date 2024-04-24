from agency_swarm import Agent
from .tools.CreateTool import CreateTool
from .tools.TestTool import TestTool


class ToolCreator(Agent):
    def __init__(self):
        super().__init__(
            description="This agent is responsible for creating new tools for the agency using python code.",
            instructions="./instructions.md",
            tools=[CreateTool, TestTool],
            temperature=0,
        )


