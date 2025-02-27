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

        if self._shared_state.get("agency_path"):
            target_path = self._shared_state.get("agency_path")
        elif self.agency_name:
            target_path_candidate = f"./{self.agency_name}"
            if os.path.isdir(target_path_candidate):
                target_path = target_path_candidate
            else:
                raise FileNotFoundError(
                    f"Directory {target_path_candidate} does not exist. Please create the agency folder or specify the correct agency_path in shared_state."
                )
        else:
            raise ValueError(
                "Please specify the agency name or set the agency_path in shared_state."
            )

        with change_directory(target_path):
            with open("agency_manifesto.md", "r") as f:
                manifesto = f.read()

        self._shared_state.set("manifesto_read", True)

        return manifesto
