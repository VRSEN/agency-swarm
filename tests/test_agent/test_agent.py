from agency_swarm.agents import BaseAgent


class TestAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Test Agent",
            description="Test Agent",
            instructions="./instructions.md",
            files_folder="./files",
            tools=[]
        )
