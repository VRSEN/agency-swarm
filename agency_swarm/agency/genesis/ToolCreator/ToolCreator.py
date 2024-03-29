from agency_swarm import Agent


class ToolCreator(Agent):
    def __init__(self):
        super().__init__(
            description="This agent is responsible for creating new tools for the agency using python code.",
            tools_folder="./tools",
            instructions="./instructions.md",
        )


