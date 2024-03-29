from agency_swarm import Agent


class AgentCreator(Agent):

    def __init__(self):
        super().__init__(
            description="This agent is responsible for creating new agents for the agency.",
            tools_folder="./tools",
            instructions="./instructions.md"
        )