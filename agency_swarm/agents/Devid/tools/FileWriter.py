import os

from agency_swarm.tools import BaseTool
from pydantic import Field


class FileWriter(BaseTool):
    """Allows you to write new files or modify existing files."""
    chain_of_thought: str = Field(
        ..., description="Please think step-by-step about what needs to be written to the file in order for the program to match the requirements.",
        exclude=True,
    )
    file_path: str = Field(
        ..., description="The path of the file to write or modify. Will create directories if they don't exist."
    )
    content: str = Field(
        ..., description="The full content of the file to write. Content must not be truncated and must represent a correct "
                         "functioning program with all the correct imports."
    )

    def run(self):
        try:
            # create directories if they don't exist
            dir_path = os.path.dirname(self.file_path)
            os.makedirs(dir_path, exist_ok=True)

            with open(self.file_path, 'w') as file:
                file.write(self.content)
            return f'Successfully wrote to file: {self.file_path}. Please make sure to build the app next to ensure that there are no errors.'
        except Exception as e:
            return f'Error writing to file: {e}'
