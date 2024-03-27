from agency_swarm.agents import Agent


class ItineraryPlannerAgent(Agent):
    def __init__(self):
        super().__init__(
            name="ItineraryPlannerAgent",
            description="Creates a detailed 3-day itinerary for the chosen city, including tourist spots, restaurant bookings, local guide arrangements, along with budget and packing suggestions. Accesses tourism databases, local guides directories, restaurant review platforms, and budget management tools for a comprehensive trip plan.",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[],
            tools_folder="./tools"
        )
