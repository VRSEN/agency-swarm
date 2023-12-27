import os

from pydantic import Field, field_validator

from agency_swarm import BaseTool


class CreateManifesto(BaseTool):
    """
    This tool reads a manifesto for the agency being created from a markdown file.
    """

    def run(self):
        # read manifesto from manifesto.md file
        with open("manifesto.md", "r") as f:
            manifesto = f.read()

        return manifesto

