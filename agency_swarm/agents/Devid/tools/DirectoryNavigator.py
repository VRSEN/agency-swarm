import os
from pydantic import Field, model_validator, field_validator

from agency_swarm.tools import BaseTool


class DirectoryNavigator(BaseTool):
    """Allows you to navigate directories. Do not use this tool more than once at a time.
    You must finish all tasks in the current directory before navigating into new directory."""
    path: str = Field(
        ..., description="The path of the directory to navigate to."
    )
    create: bool = Field(
        False, description="If True, the directory will be created if it does not exist."
    )
    one_call_at_a_time: bool = True

    def run(self):
        try:
            os.chdir(self.path)
            return f'Successfully changed directory to: {self.path}'
        except Exception as e:
            return f'Error changing directory: {e}'

    @field_validator("create", mode="before")
    @classmethod
    def validate_create(cls, v):
        if not isinstance(v, bool):
            if v.lower() == "true":
                return True
            elif v.lower() == "false":
                return False
        return v

    @model_validator(mode='after')
    def validate_path(self):
        if not os.path.isdir(self.path):
            if "/mnt/data" in self.path:
                raise ValueError("You tried to access an openai file directory with a local directory reader tool. " +
                                 "Please use the `myfiles_browser` tool to access openai files instead. " +
                                 "Your local files are most likely located in your current directory.")

            if self.create:
                os.makedirs(self.path)
            else:
                raise ValueError(f"The path {self.path} does not exist. Please provide a valid directory path. " +
                                 "If you want to create the directory, set the `create` parameter to True.")

        return self
