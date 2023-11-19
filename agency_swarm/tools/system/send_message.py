from typing import Literal

from agency_swarm.tools import BaseTool
from pydantic import Field


class SendMessage(BaseTool):
    """Send messages to other specialized agents in this group chat."""
    recepient: Literal['code_assistant'] = Field(..., description="code_assistant is a world class programming AI capable of executing python code.")
    message: str = Field(...,
        description="Specify the task required for the recipient agent to complete. Focus instead on clarifying what the task entails, rather than providing detailed instructions.")

    def run(self):
      pass