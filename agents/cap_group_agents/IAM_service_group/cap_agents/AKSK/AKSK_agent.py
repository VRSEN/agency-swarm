from agency_swarm.agents import Agent


class AKSK(Agent):
    def __init__(self):
        super().__init__(
            name="AKSK_Agent",
            description="负责获取华为云AK/SK信息",
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
