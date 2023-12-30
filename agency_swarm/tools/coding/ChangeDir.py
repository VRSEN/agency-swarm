from pydantic import Field

from agency_swarm import BaseTool

import os


class ChangeDir(BaseTool):
    """
    This tool changes the current working directory to the specified path.
    """
    path: str = Field(
        ..., description="Path to the directory to change to.",
        examples=["./some_folder", "../../some_folder"]
    )

    def run(self):
        # change directory
        os.chdir(self.path)

        return f"Current working directory has been changed to {self.path}."
