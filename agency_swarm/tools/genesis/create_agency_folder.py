from pydantic import Field

from agency_swarm import BaseTool

import os


class CreateAgencyFolder(BaseTool):
    """
    This tool creates an agency folder in local directory according to its name.
    """
    agency_name: str = Field(
        ..., description="Name of the agency to be created.",
        examples=["AgencyName"]
    )

    def run(self):
        folder_path = "./" + self.agency_name + "/"
        # create folder
        os.mkdir(folder_path)

        os.chdir(folder_path)

        # create init file
        with open("__init__.py", "w") as f:
            f.write("")

        return f"Agency folder has been created in {folder_path}."
