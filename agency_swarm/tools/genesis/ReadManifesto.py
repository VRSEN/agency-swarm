import os

from pydantic import Field, field_validator

from agency_swarm import BaseTool


class ReadManifesto(BaseTool):
    """
    This tool reads a manifesto for the agency being created from a markdown file.
    """

    def run(self):
        # read manifesto from manifesto.md file
        try:
            with open("agency_manifesto.md", "r") as f:
                manifesto = f.read()
        except FileNotFoundError:
            return (f"Manifesto file not found. Please change your current working directory {os.getcwd()} to the "
                    f"root agency folder with ChangeDir tool.")

        return manifesto

