from agency_swarm.agents import Agent


class CEOAgent(Agent):
    def __init__(self):
        super().__init__(
            name="CEOAgent",
            description="The CEO Agent oversees and coordinates all operations within the TripPlanner Agency, ensuring the creation and execution of personalized travel itineraries.",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[],
            tools_folder="./tools"
        )
