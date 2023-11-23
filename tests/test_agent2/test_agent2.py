from agency_swarm.agents import Agent


class TestAgent2(Agent):
    def __init__(self):
        super().__init__()
        self.description = "Test Agent"
        self.instructions = "./instructions.md"
