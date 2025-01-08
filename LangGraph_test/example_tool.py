from agency_swarm.tools import BaseTool
from pydantic import Field

class RepeateMessage(BaseTool):
    """repeat the message"""
    repeat_message: str = Field(
        ..., description="the message needed to be repeated."
    )
    def run(self):
        print(self.repeat_message)
        return "repeat:" + self.repeat_message
