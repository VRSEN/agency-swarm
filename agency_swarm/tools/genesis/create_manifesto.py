import os

from pydantic import Field, field_validator

from agency_swarm import BaseTool


class CreateManifesto(BaseTool):
    """
    This tool creates a manifesto for the agency and saves it to a markdown file.
    """
    agency_folder_path: str = Field(
        ..., description="Path to the folder for the agency created with CreateFolder tool.",
        examples=["./agency_name"]
    )
    manifesto: str = Field(
        ..., description="Manifesto for the agency, describing it's goals and additional context shared by all agents "
                         "in markdown format."
    )

    def run(self):
        # save manifesto to manifesto.md file
        with open("manifesto.md", "w") as f:
            f.write(self.manifesto)

        return "Manifesto has been written to ./manifesto.md file."

    @field_validator("agency_folder_path", mode='after')
    @classmethod
    def validate_agency_name(cls, v):
        if not os.path.exists(v):
            raise ValueError(f"Agency folder path {v} does not exist.")
        return v
