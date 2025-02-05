import os
import shutil

from pydantic import Field

from agency_swarm.tools import BaseTool


class FileCopier(BaseTool):
    """
    FileCopier is a tool designed to copy files from a source path to a destination path. 
    If the destination directory does not exist, it will be created.
    """

    source_path: str = Field(
        ...,
        description="The full path of the file to copy, including the file name and extension.",
    )
    destination_path: str = Field(
        ...,
        description="The destination path where the file should be copied, including the new file name and extension if changing.",
    )

    def run(self):
        """
        Executes the file copying operation from the source path to the destination path.
        It checks if the destination directory exists and creates it if necessary, then copies the file.
        """
        if not os.path.exists(self.source_path):
            return f"Source file does not exist at {self.source_path}"

        # Ensure the destination directory exists
        destination_dir = os.path.dirname(self.destination_path)
        if not os.path.exists(destination_dir):
            os.makedirs(destination_dir)

        # Copy the file
        shutil.copy2(self.source_path, self.destination_path)

        return f"File copied successfully from {self.source_path} to {self.destination_path}"
