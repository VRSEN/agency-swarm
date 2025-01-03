from agency_swarm.agents import Agent


class HarddiskAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Harddisk Agent",
            description="Harddisk Agent负责ECS硬盘配置。",
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
