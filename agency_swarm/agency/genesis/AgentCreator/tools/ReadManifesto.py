import os

from agency_swarm import BaseTool


class ReadManifesto(BaseTool):
    """
    This tool reads a manifesto for the agency being created from a markdown file.
    """

    def run(self):
        os.chdir(self.shared_state.get("agency_path"))
        with open("agency_manifesto.md", "r") as f:
            manifesto = f.read()

        os.chdir(self.shared_state.get("default_folder"))

        self.shared_state.set("manifesto_read", True)

        return manifesto
