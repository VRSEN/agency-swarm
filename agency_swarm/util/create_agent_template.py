import os


def create_agent_template(agent_name=None,
                          agent_description=None,
                          path="./",
                          instructions=None,
                          code_interpreter=False,
                          use_txt=False):
    if not agent_name:
        agent_name = input("Enter agent name: ")
    if not agent_description:
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

    # create agent file
    class_name = agent_name.title().replace(" ", "").strip()
    with open(path + folder_name + ".py", "w") as f:
        f.write(agent_template.format(
            class_name=class_name,
            agent_name=agent_name,
            agent_description=agent_description,
            ext="md" if not use_txt else "txt",
            code_interpreter="CodeInterpreter" if code_interpreter else "",
            code_interpreter_import="from agency_swarm.tools import CodeInterpreter" if code_interpreter else ""
        ))

    # create init file
    with open(path + "__init__.py", "w") as f:
        f.write(f"from .{folder_name} import {class_name}")

    # create instructions file
    instructions_path = "instructions.md" if not use_txt else "instructions.txt"
    with open(path + instructions_path, "w") as f:
        if instructions:
            f.write(instructions)
        else:
            f.write("Below are the specific instructions tailored for you to effectively carry out your assigned role:\n\n")

    # create files folder
    os.mkdir(path + "files")

    # create tools file
    with open(path + "tools.py", "w") as f:
        f.write(tools_template)

    print("Agent folder created successfully.")
    print(f"Import it with: from {folder_name} import {class_name}")


agent_template = """
before_names = dir()
from .tools import *
current_names = dir()
imported_tool_objects = [globals()[name] for name in current_names if name not in before_names and isinstance(globals()[name], type) and issubclass(globals()[name], BaseTool)]
from agency_swarm.agents import Agent
{code_interpreter_import}

class {class_name}(Agent):
    def __init__(self):
        super().__init__(
            name="{agent_name}",
            description="{agent_description}",
            instructions="./instructions.{ext}",
            files_folder="./files",
            tools=imported_tool_objects + [{code_interpreter}] 
        )
"""

tools_template = """from agency_swarm.tools import BaseTool
from pydantic import Field


class ExampleTool(BaseTool):
    \"\"\"Enter your tool description here. It should be informative for the Agent.\"\"\"
    content: str = Field(
        ..., description="Enter parameter descriptions using pydantic for the model here."
    )
    
    def run(self):
        # Enter your tool code here. It should return a string.
        
        # do_something(self.content)
        
        return "Tool output"
"""
