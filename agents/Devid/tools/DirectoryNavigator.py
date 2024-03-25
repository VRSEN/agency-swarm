from agency_swarm.tools import BaseTool
from pydantic import Field
import os


class DirectoryNavigator(BaseTool):
    """Allows the WebDeveloper agent to navigate directories."""
    path: str = Field(
        ..., description="The path of the directory to navigate to."
    )

    def run(self):
        try:
            os.chdir(self.path)
            return f'Successfully changed directory to: {self.path}'
        except Exception as e:
            return f'Error changing directory: {e}'
