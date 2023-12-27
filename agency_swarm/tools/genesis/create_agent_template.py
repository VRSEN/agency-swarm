from pydantic import Field

from agency_swarm import BaseTool
from agency_swarm.util import create_agent_template


class CreateAgentTemplate(BaseTool):
    """
    This tool creates a template folder for a new agent that includes boilerplage code and instructions.
    """
    agent_name: str = Field(
        ..., description="Name of the agent to be created."
    )
    agent_description: str = Field(
        ..., description="Description of the agent to be created."
    )

    def run(self):
        create_agent_template(self.agent_name, self.agent_description)

        return (f"Agent template has been created in {self.agent_name} folder. "
                f"You can navigate to the folder to start working on your agent.")