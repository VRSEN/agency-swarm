import os
from enum import Enum
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
        None, description="New line to replace the old line. Not required only for delete mode.",
        examples=["This is a new line"]
    )
    mode: Literal["replace", "insert", "delete"] = Field(
        "replace", description='Mode to use for the line change. "replace" replaces the line with the new line. '
                               '"insert" inserts the new line at the specified line number, moving the previous line down.'
                               ' "delete" deletes the specified line number.',
    )

    @model_validator(mode='after')
    def validate_new_line(self):
        mode, new_line = self.mode, self.new_line
        if mode == "delete" and new_line is not None:
            raise ValueError("new_line should not be specified for delete mode.")
        elif mode in ["replace", "insert"] and new_line is None:
            raise ValueError("new_line should be specified for replace and insert modes.")
        return self


class ChangeFile(BaseTool):
    """
    This tool changes specified lines in a file. Returns the new file contents with line numbers at the start of each line.
    """
    chain_of_thought: str = Field(
        ..., description="Please think step-by-step about the required changes to the file in order to construct a fully functioning and correct program according to the requirements.",
        exclude=True,
    )
    file_path: str = Field(
        ..., description="Path to the file with extension.",
        examples=["./file.txt", "./file.json", "../../file.py"]
    )
    changes: List[LineChange] = Field(
        ..., description="Line changes to be made to the file.",
        examples=[{"line_number": 1, "new_line": "This is a new line", "mode": "replace"}]
    )

    def run(self):
        # read file
        with open(self.file_path, "r") as f:
            file_contents = f.readlines()

            # Process changes in a way that accounts for modifications affecting line numbers
            for change in sorted(self.changes, key=lambda x: x.line_number, reverse=True):
                try:
                    if change.mode == "replace" and 0 < change.line_number <= len(file_contents):
                        file_contents[change.line_number - 1] = change.new_line + '\n'
                    elif change.mode == "insert":
                        file_contents.insert(change.line_number - 1, change.new_line + '\n')
                    elif change.mode == "delete" and 0 < change.line_number <= len(file_contents):
                        file_contents.pop(change.line_number - 1)
                except IndexError:
                    return f"Error: Line number {change.line_number} is out of the file's range."

        # write file
        with open(self.file_path, "w") as f:
            f.writelines(file_contents)

        with open(self.file_path, "r") as f:
            file_contents = f.readlines()

        # return file contents with line numbers
        return "\n".join([f"{i + 1}. {line}" for i, line in enumerate(file_contents)])

    # use field validation to ensure that the file path is valid
    @field_validator("file_path", mode='after')
    @classmethod
    def validate_file_path(cls, v: str):
        if not os.path.exists(v):
            raise ValueError("File path does not exist.")

        return v