from agency_swarm.agents import BaseAgent


class TestAgent2(BaseAgent):
    def __init__(self):
        super().__init__()
        self.description = "Test Agent"
        self.instructions = "./instructions.md"
