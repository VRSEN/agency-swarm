from agency_swarm.tools import BaseTool
from pydantic import Field


class FileReader(BaseTool):
    """This tool reads a file and returns the contents along with line numbers on the left."""
    file_path: str = Field(
        ..., description="Path to the file to read with extension.",
        examples=["./file.txt", "./file.json", "../../file.py"]
    )

    def run(self):
        # read file
        with open(self.file_path, "r") as f:
            file_contents = f.readlines()

        # return file contents
        return "\n".join([f"{i + 1}. {line}" for i, line in enumerate(file_contents)])
