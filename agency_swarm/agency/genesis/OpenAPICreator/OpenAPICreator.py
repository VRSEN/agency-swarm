from agency_swarm import Agent


class OpenAPICreator(Agent):
    def __init__(self):
        super().__init__(
            description="This agent is responsible for creating new tools from an OpenAPI specifications.",
            tools_folder="./tools",
            instructions="./instructions.md"
        )