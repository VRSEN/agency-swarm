from agency_swarm.tools import BaseTool
from pydantic import Field, field_validator


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

    @field_validator("file_path", mode="after")
    @classmethod
    def validate_file_path(cls, v):
        if "file-" in v:
            raise ValueError("You tried to access an openai file with a wrong file reader tool. "
                             "Please use the `myfiles_browser` tool to access openai files instead."
                             "This tool is only for reading local files.")
        return v
