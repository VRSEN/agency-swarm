from agency_swarm.agents import Agent


class RecommendAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Recommend Agent",
            description="Recommend Agent负责进行华为云ECS规格推荐。",
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
