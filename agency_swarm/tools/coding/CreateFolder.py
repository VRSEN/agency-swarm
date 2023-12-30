from pydantic import Field

from agency_swarm import BaseTool

import os


class CreateFolder(BaseTool):
    """
    This tool creates a folder at the specified path.
    """
    folder_path: str = Field(
        ..., description="Path to the folder to create.",
        examples=["./new_dir"]
    )

    def run(self):
        # create folder
        os.mkdir(self.folder_path)

        return f"Folder {self.folder_path} has been created."
