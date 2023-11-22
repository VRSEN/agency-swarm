from agency_swarm.agents import BaseAgent


class Ceo(BaseAgent):
    def __init__(self):
        super().__init__(
            name="CEO",
            description="Ceo Agent",
            instructions="./instructions.md"
        )
