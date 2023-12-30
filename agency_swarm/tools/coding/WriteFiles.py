import os
from typing import List

from pydantic import Field

from agency_swarm import BaseTool


class File(BaseTool):
    """
    File to be written to the disk with an appropriate name and file path, containing code that can be saved and executed locally at a later time.
    """
    file_name: str = Field(
        ...,
        description="The name of the file including the extension and the file path from your current directory if needed."
    )
    body: str = Field(..., description="Correct contents of a file")

    def run(self):
        # Extract the directory path from the file name
        directory = os.path.dirname(self.file_name)

        # If the directory is not empty, check if it exists and create it if not
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

        # Write the file
        with open(self.file_name, "w") as f:
            f.write(self.body)

        return "File written to " + self.file_name


class WriteFiles(BaseTool):
    """
    Set of files that represent a complete and correct program.
    """
    chain_of_thought: str = Field(...,
                                  description="Think step by step to determine the correct actions that are needed to implement the program.")
    files: List[File] = Field(..., description="List of files")

    def run(self):
        outputs = []
        for file in self.files:
            outputs.append(file.run())

        return str(outputs)
