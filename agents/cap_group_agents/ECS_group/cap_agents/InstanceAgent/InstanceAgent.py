from agency_swarm.agents import Agent


class InstanceAgent(Agent):
    def __init__(self):
        super().__init__(
            name="Instance Agent",
            description="Instance Agent负责创建、删除、查询、修改、迁移、启动、停止、重启ECS实例。",
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
