from pydantic import Field

from agency_swarm import BaseTool

import os


class CreateAgencyFolder(BaseTool):
    """
    This tool creates an agency folder.
    """
    agency_name: str = Field(
        ..., description="Name of the agency to be created.",
        examples=["AgencyName"]
    )
    agency_chart: str = Field(
        ..., description="Agency chart to be passed into the Agency class.",
        examples=["[ceo, [ceo, dev], [ceo, va], [dev, va] ]"]
    )
    manifesto: str = Field(
        ..., description="Manifesto for the agency, describing it's goals and additional context shared by all agents "
                         "in markdown format."
    )

    def run(self):
        folder_path = "./" + self.agency_name + "/"
        # create folder
        os.mkdir(folder_path)

        os.chdir(folder_path)

        # check that agency chart is valid
        if not self.agency_chart.startswith("[") or not self.agency_chart.endswith("]"):
            raise ValueError("Agency chart must be a list of lists.")

        # add new lines after every comma, except for those inside second brackets
        # must transform from "[ceo, [ceo, dev], [ceo, va], [dev, va] ]"
        # to "[ceo, [ceo, dev],\n [ceo, va],\n [dev, va] ]"
        agency_chart = self.agency_chart.replace("],", "],\n")

        # create init file
        with open("__init__.py", "w") as f:
            f.write("")

        # create agency.py
        with open("agency.py", "w") as f:
            f.write("from agency_swarm import Agency\n\n\n")
            f.write(f"agency = Agency({agency_chart},\nshared_instructions='./agency_manifesto.md')\n\n")
            f.write("if __name__ == '__main__':\n")
            f.write("    agency.demo_gradio()\n")

        # write manifesto
        path = os.path.join("agency_manifesto.md")
        with open(path, "w") as f:
            f.write(self.manifesto)

        return f"Agency folder has been created in {folder_path}."


