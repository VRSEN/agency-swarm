from agency_swarm.tools import BaseTool
from pydantic import Field


class ExampleTool1(BaseTool):
    """Enter your tool description here. It should be informative for the Agent."""
    content: str = Field(
        ..., description="Enter parameter descriptions using pydantic for the model here."
    )

    def run(self):
        # Enter your tool code here. It should return a string.

        # do_something(self.content)

        return "Tool output"