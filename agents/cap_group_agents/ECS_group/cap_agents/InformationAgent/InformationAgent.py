from agency_swarm.agents import Agent


class InformationAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Information Agent",
            description="Information Agent负责查询华为云ECS相关的规格信息。",
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
