from agency_swarm.agents import Agent
from agency_swarm.tools import CodeInterpreter

class AccommodationsAndActivitiesAgent(Agent):
    def __init__(self):
        super().__init__(
            name="AccommodationsAndActivitiesAgent",
            description="This agent specializes in recommending the best accommodations, restaurants, and activities based on the destination and user interests to ensure memorable travel experiences.",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[CodeInterpreter],
            tools_folder="./tools"
        )
