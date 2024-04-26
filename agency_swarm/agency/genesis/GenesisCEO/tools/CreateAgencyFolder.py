import shutil
from pathlib import Path

from pydantic import Field, field_validator

import agency_swarm.agency.genesis.GenesisAgency
from agency_swarm import BaseTool

import os


class CreateAgencyFolder(BaseTool):
    """
    This tool creates or modifies an agency folder. You can use it again with the same agency_name to modify a previously created agency, if the user wants to change the agency chart or the manifesto.
    """
    agency_name: str = Field(
        ..., description="Name of the agency to be created. Must not contain spaces or special characters.",
        examples=["AgencyName", "MyAgency", "ExampleAgency"]
    )
    agency_chart: str = Field(
        ..., description="Agency chart to be passed into the Agency class.",
        examples=["[ceo, [ceo, dev], [ceo, va], [dev, va]]"]
    )
    manifesto: str = Field(
        ..., description="Manifesto for the agency, describing its goals and additional context shared by all agents "
                         "in markdown format. It must include information about the working environment, the mission "
                         "and the goals of the agency. Do not add descriptions of the agents themselves or the agency structure.",
    )

    def run(self):
        if not self.shared_state.get("default_folder"):
            self.shared_state.set('default_folder', Path.cwd())

        if self.shared_state.get("agency_name") is None:
            os.mkdir(self.agency_name)
            os.chdir("./" + self.agency_name)
            self.shared_state.set("agency_name", self.agency_name)
            self.shared_state.set("agency_path", Path("./").resolve())
        elif self.shared_state.get("agency_name") == self.agency_name and os.path.exists(self.shared_state.get("agency_path")):
            os.chdir(self.shared_state.get("agency_path"))
            for file in os.listdir():
                if file != "__init__.py" and os.path.isfile(file):
                    os.remove(file)
        else:
            os.mkdir(self.shared_state.get("agency_path"))
            os.chdir("./" + self.agency_name)

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
            f.write(agency_py.format(agency_chart=agency_chart))

        # write manifesto
        path = os.path.join("agency_manifesto.md")
        with open(path, "w") as f:
            f.write(self.manifesto)

        os.chdir(self.shared_state.get('default_folder'))

        return f"Agency folder has been created. You can now tell AgentCreator to create agents for {self.agency_name}.\n"


agency_py = """from agency_swarm import Agency


agency = Agency({agency_chart},
                shared_instructions='./agency_manifesto.md', # shared instructions for all agents
                max_prompt_tokens=25000, # default tokens in conversation for all agents
                temperature=0.3, # default temperature for all agents
                )
                
if __name__ == '__main__':
    agency.demo_gradio()
"""