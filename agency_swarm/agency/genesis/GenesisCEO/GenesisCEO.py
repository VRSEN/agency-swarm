from pathlib import Path

from agency_swarm import Agent
from .tools.CreateAgencyFolder import CreateAgencyFolder
from .tools.FinalizeAgency import FinalizeAgency
from .tools.ReadRequirements import ReadRequirements


class GenesisCEO(Agent):
    def __init__(self):
        super().__init__(
            description="Acts as the overseer and communicator across the agency, ensuring alignment with the "
                        "agency's goals.",
            instructions="./instructions.md",
            tools=[CreateAgencyFolder, FinalizeAgency, ReadRequirements],
            temperature=0.4,
        )


