import os

from pydantic import Field, field_validator

from agency_swarm import BaseTool


class CreateManifesto(BaseTool):
    """
    This tool creates a manifesto for the agency and saves it to a markdown file.
    """
    manifesto: str = Field(
        ..., description="Manifesto for the agency, describing it's goals and additional context shared by all agents "
                         "in markdown format."
    )

    def run(self):
        path = os.path.join("manifesto.md")
        # save manifesto to manifesto.md file
        with open(path, "w") as f:
            f.write(self.manifesto)

        return f"Manifesto has been written to {path} file."