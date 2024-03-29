from agency_swarm import Agent


class GenesisCEO(Agent):
    def __init__(self):
        super().__init__(
            description="Acts as the overseer and communicator across the agency, ensuring alignment with the "
                        "agency's goals.",
            tools_folder="./tools",
            instructions="./instructions.md"
        )


