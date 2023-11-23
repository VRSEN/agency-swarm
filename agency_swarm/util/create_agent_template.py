import os


def create_agent_template(path="./", use_txt=False):
    agent_name = input("Enter agent name: ")
    agent_description = input("Enter agent description: ")

    # create manifesto if it doesn't exist
    agency_manifesto = "agency_manifesto.md" if not use_txt else "agency_manifesto.txt"
    if not os.path.isfile(os.path.join(path, agency_manifesto)):
        with open(os.path.join(path, agency_manifesto), "w") as f:
            f.write("As a member of our Agency, please find below the guiding principles and values that constitute "
                    "our Agency Manifesto:\n\n")

    # create folder
    folder_name = agent_name.lower().replace(" ", "_").strip()
    path = os.path.join(path, folder_name) + "/"
    if os.path.isdir(path):
        raise Exception("Folder already exists.")
    os.mkdir(path)

    # create init file
    with open(path + "__init__.py", "w") as f:
        f.write("from . import *")

    # create agent file
    class_name = agent_name.title().replace(" ", "").strip()
    with open(path + class_name + ".py", "w") as f:
        f.write(agent_template.format(
            class_name=class_name,
            agent_name=agent_name,
            agent_description=agent_description,
            ext="md" if not use_txt else "txt"
        ))

    # create instructions file
    instructions = "instructions.md" if not use_txt else "instructions.txt"
    with open(path + instructions, "w") as f:
        f.write("Below are the specific instructions tailored for you to effectively carry out your assigned role:\n\n")

    # create files folder
    os.mkdir(path + "files")

    # create tools file
    with open(path + "tools.py", "w") as f:
        f.write(tools_template)

    print("Agent folder created successfully.")
    print(f"Import it with: from {folder_name} import {class_name}")


agent_template = """from agency_swarm.agents import BaseAgent

# from agency_swarm.tools import Retrieval, CodeInterpreter
from .tools import *


class {class_name}(BaseAgent):
    def __init__(self):
        super().__init__(
            name="{agent_name}",
            description="{agent_description}",
            instructions="./instructions.{ext}",
            files_folder="./files",
            tools=[]  # add tools here like tools=[ExampleTool]
        )
"""

tools_template = """from agency_swarm.tools import BaseTool
from pydantic import Field


class ExampleTool(BaseTool):
    \"\"\"Enter your tool description here. It should be informative for the model.\"\"\"
    content: str = Field(
        ..., description="Enter parameter descriptions using pydantic for the model here."
    )
    
    def run(self):
        \"\"\"Enter your code for tool execution here.\"\"\"
        pass
"""

