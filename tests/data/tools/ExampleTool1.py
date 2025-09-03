from pydantic import Field

from agency_swarm.tools import BaseTool


class ExampleTool1(BaseTool):
    """Simple echo tool used by tests."""

    content: str = Field(..., description="Text that will be returned by the tool.")

    def run(self) -> str:
        """Return the provided content unchanged."""

        return self.content
