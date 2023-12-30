import os
from typing import Literal, Optional, List

from instructor import OpenAISchema
from pydantic import Field, model_validator, field_validator

from agency_swarm import BaseTool


class LineChange(OpenAISchema):
    """
    Line changes to be made.
    """
    line_number: int = Field(
        ..., description="Line number to change.",
        examples=[1, 2, 3]
    )
    new_line: Optional[str] = Field(
        ..., description="New line to replace the old line. Not required only for delete mode.",
        examples=["This is a new line"]
    )
    mode: Literal["replace", "insert", "delete"] = Field(
        "replace", description='Mode to use for the line change. "replace" replaces the line with the new line, '
                               '"insert" inserts the new line at the specified line number, and "delete" deletes the '
                               "specified line number.",
    )

    @model_validator(mode='after')
    def validate_new_line(self):
        if self.mode == "delete":
            if "new_line" in self:
                raise ValueError("new_line should not be specified for delete mode.")
        else:
            if not self.new_line:
                raise ValueError("new_line should be specified for replace and insert modes.")

        return self


class ChangeLines(BaseTool):
    """
    This tool changes specified lines in a file. Returns the new file contents.
    """
    file_path: str = Field(
        ..., description="Path to the file with extension.",
        examples=["./file.txt", "./file.json", "../../file.py"]
    )
    changes: List[LineChange] = Field(
        ..., description="Line changes to be made to the file.",
        examples=[LineChange(line_number=1, new_line="This is a new line").model_dump()]
    )

    def run(self):
        # read file
        with open(self.file_path, "r") as f:
            file_contents = f.readlines()

        # make changes
        for change in self.changes:
            if change.mode == "replace":
                file_contents[change.line_number - 1] = change.new_line
            elif change.mode == "insert":
                file_contents.insert(change.line_number - 1, change.new_line)
            elif change.mode == "delete":
                file_contents.pop(change.line_number - 1)

        # write file
        with open(self.file_path, "w") as f:
            f.writelines(file_contents)

        # return file contents with line numbers
        return "\n".join([f"{i + 1}. {line}" for i, line in enumerate(file_contents)])

    # use field validation to ensure that the file path is valid
    @field_validator("file_path", mode='after')
    @classmethod
    def validate_file_path(cls, v: str):
        if not os.path.exists(v):
            raise ValueError("File path does not exist.")

        return v
