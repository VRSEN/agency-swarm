from agency_swarm import Agent
from .tools.CreateAgencyFolder import CreateAgencyFolder
from .tools.FinalizeAgency import FinalizeAgency


class GenesisCEO(Agent):

    def __init__(self, **kwargs):
        # Initialize tools in kwargs if not present
        if 'tools' not in kwargs:
            kwargs['tools'] = []

        kwargs['description'] = "Acts as the overseer and communicator across the agency, ensuring alignment with the agency's goals."

        # Add required tools
        kwargs['tools'].extend([CreateAgencyFolder, FinalizeAgency])

        # Set instructions
        kwargs['instructions'] = "./instructions.md"

        # Initialize the parent class
        super().__init__(**kwargs)


