from agency_swarm.agents import Agent


class Ceo(Agent):
    def __init__(self):
        super().__init__(
            name="CEO",
            description="Ceo Agent",
            instructions="./instructions.md"
        )
