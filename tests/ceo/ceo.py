from agency_swarm.agents import BaseAgent


class Ceo(BaseAgent):
    def __init__(self):
        super().__init__()
        self.name = "Ceo"
        self.description = "Ceo Agent"
        self.instructions = "./instructions.md"
