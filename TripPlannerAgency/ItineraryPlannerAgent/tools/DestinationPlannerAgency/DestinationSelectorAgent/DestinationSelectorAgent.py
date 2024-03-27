from agency_swarm.agents import Agent


class DestinationSelectorAgent(Agent):
    def __init__(self):
        super().__init__(
            name="DestinationSelectorAgent",
            description="Responsible for selecting the best city based on user preferences, weather conditions, seasonality, and overall costs. Utilizes APIs for weather forecasts, seasonal tourist information, and cost-of-living data to ensure the destination meets user criteria in terms of timing, budget, and interests.",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[],
            tools_folder="./tools"
        )
