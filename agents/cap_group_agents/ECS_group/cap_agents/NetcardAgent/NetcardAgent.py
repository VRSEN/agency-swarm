from agency_swarm.agents import Agent


class NetcardAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Netcard Agent",
            description="Netcard Agent负责ECS网卡配置。。",
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
