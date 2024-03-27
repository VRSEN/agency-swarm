from agency_swarm.agents import Agent


class CEOAgent(Agent):
    def __init__(self):
        super().__init__(
            name="CEOAgent",
            description="The CEOAgent acts as the primary contact for users, collecting initial preferences such as travel dates, interests, and budget constraints. It coordinates with the DestinationSelectorAgent and ItineraryPlannerAgent to finalize the travel plan. This agent processes user inputs and manages communication with other agents.",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[],
            tools_folder="./tools"
        )
