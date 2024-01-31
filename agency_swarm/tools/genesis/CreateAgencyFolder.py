import shutil

from pydantic import Field, field_validator

from agency_swarm import BaseTool

import os

current_agency_name = None

class CreateAgencyFolder(BaseTool):
    """
    This tool creates or modifies an agency folder. You can use it again with the same agency_name to modify a previously created agency, if the user wants to change the agency chart or the manifesto.
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

        global current_agency_name
        if current_agency_name is not None:
            if os.getcwd().strip("/").strip("\\").endswith(current_agency_name):
                os.chdir("..")
                shutil.rmtree(current_agency_name)

        current_agency_name = self.agency_name

        # create folder
        os.mkdir(folder_path)

        os.chdir(folder_path)

        # check that agency chart is valid
        if not self.agency_chart.startswith("[") or not self.agency_chart.endswith("]"):
            raise ValueError("Agency chart must be a list of lists, except for the first agents.")

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

    @field_validator('agency_name', mode='after')
    @classmethod
    def check_agency_name(cls, v):
        global current_agency_name

        if os.path.exists("./" + v):
                raise ValueError("Agency with this name already exists.")

        if current_agency_name is not None:
            if current_agency_name != v:
                raise ValueError("You can only create 1 agency at a time. Please tell the user to restart the system if he wants to create a new agency or use the same agency_name to modify an exisiting agency.")

            if not os.getcwd().strip("/").endswith(current_agency_name):
                raise ValueError("Please tell the user to restart the system if he wants to create a new agency.")

        return v


