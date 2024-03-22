from agency_swarm.tools import BaseTool
from pydantic import Field
import os


class ReadRequirements(BaseTool):
    """
    Use this tool to read the agency requirements if user provides them as a file.
    """

    file_path: str = Field(
        ..., description="The path to the file that needs to be read."
    )

    def run(self):
        """
        Checks if the file exists, and if so, opens the specified file, reads its contents, and returns them.
        If the file does not exist, raises a ValueError.
        """
        if not os.path.exists(self.file_path):
            raise ValueError(f"File path does not exist: {self.file_path}")

        try:
            with open(self.file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            return content
        except Exception as e:
            return f"An error occurred while reading the file: {str(e)}"
