from agency_swarm.agents import Agent
from agency_swarm.tools import CodeInterpreter

class ItineraryPlannerAgent(Agent):
    def __init__(self):
        super().__init__(
            name="ItineraryPlannerAgent",
            description="The Itinerary Planner Agent specializes in creating detailed, personalized 7-day travel itineraries, focusing on user preferences, weather conditions, safety, and optimal travel seasons.",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[CodeInterpreter],
            tools_folder="./tools"
        )
