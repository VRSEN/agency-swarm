from agency_swarm.agents import Agent


class VpcPlanner(Agent):
    def __init__(self):
        super().__init__(
            name="Vpc Planner",
            description="Vpc Planner负责调用vpc，子网，安全组有关的agent。",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[],
            tools_folder="./tools",
            temperature=0.3,
            max_prompt_tokens=25000,
        )
        
    def response_validator(self, message):
        return message
