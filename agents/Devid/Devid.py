from agency_swarm.agents import Agent
from agency_swarm.tools import CodeInterpreter


class Devid(Agent):
    def __init__(self):
        super().__init__(
            name="Devid",
            description="Devid is an AI software engineer capable of performing advanced coding tasks.",
            instructions="./instructions.md",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[CodeInterpreter],
            tools_folder="./tools"
        )
