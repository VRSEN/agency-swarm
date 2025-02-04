import os

from pydantic import Field

from agency_swarm import BaseTool
from agency_swarm.agency.genesis.util import change_directory


class ReadManifesto(BaseTool):
    """
    This tool reads a manifesto for the agency being created from a markdown file.
    """

    agency_name: str = Field(
        None,
        description="Name of the agency to create the tool for. Defaults to the agency currently being created.",
    )

    def run(self):
        if not self._shared_state.get("default_folder"):
            self._shared_state.set("default_folder", os.getcwd())

        if not self._shared_state.get("agency_path") and not self.agency_name:
            raise ValueError(
                "Please specify the agency name. Ask user for clarification if needed."
            )

        target_path = (
            self.agency_name
            and f"./{self.agency_name}"
            or self._shared_state.get("agency_path")
        )

        with change_directory(target_path):
            with open("agency_manifesto.md", "r") as f:
                manifesto = f.read()

        self._shared_state.set("manifesto_read", True)

        return manifesto
