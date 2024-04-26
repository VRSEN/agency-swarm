import os
import shutil
from typing import List

from pydantic import Field, model_validator

from agency_swarm import BaseTool
from agency_swarm.agency.genesis.util import check_agency_path
from agency_swarm.util import create_agent_template

allowed_tools: List = ["CodeInterpreter"]

web_developer_example_instructions = """# Web Developer Agent Instructions

You are an agent that builds responsive web applications using Next.js and Material-UI (MUI). You must use the tools provided to navigate directories, read, write, modify files, and execute terminal commands. 

### Primary Instructions:
1. Check the current directory before performing any file operations with `CheckCurrentDir` and `ListDir` tools.
2. Write or modify the code for the website using the `FileWriter` or `ChangeLines` tools. Make sure to use the correct file paths and file names. Read the file first if you need to modify it.
3. Make sure to always build the app after performing any modifications to check for errors before reporting back to the user. Keep in mind that all files must be reflected on the current website
4. Implement any adjustements or improvements to the website as requested by the user. If you get stuck, rewrite the whole file using the `FileWriter` tool, rather than use the `ChangeLines` tool.
"""


class CreateAgentTemplate(BaseTool):
    """
    This tool creates a template folder for a new agent. Always use this tool first, before creating tools or APIs for the agent.
    """
    agent_name: str = Field(
        ..., description="Name of the agent to be created. Cannot include special characters or spaces."
    )
    agent_description: str = Field(
        ..., description="Description of the agent to be created."
    )
    instructions: str = Field(
        ..., description="Instructions for the agent to be created in markdown format. "
                         "Instructions should include a decription of the role and a specific step by step process "
                         "that this agent need to perform in order to execute the tasks. "
                         "The process must also be aligned with all the other agents in the agency. Agents should be "
                         "able to collaborate with each other to achieve the common goal of the agency.",
        examples=[
            web_developer_example_instructions,
        ]
    )
    default_tools: List[str] = Field(
        [], description=f"List of default tools to be included in the agent. Possible values are {allowed_tools}."
                        f"CodeInterpreter allows the agent to execute python code in a remote python environment.",
        example=["CodeInterpreter"],
    )
    agency_name: str = Field(
        None, description="Name of the agency to create the tool for. Defaults to the agency currently being created."
    )

    def run(self):
        if not self.shared_state.get("manifesto_read"):
            raise ValueError("Please read the manifesto first with the ReadManifesto tool.")

        self.shared_state.set("agent_name", self.agent_name)

        os.chdir(self.shared_state.get("agency_path"))

        # remove folder if it already exists
        if os.path.exists(self.agent_name):
            shutil.rmtree(self.agent_name)

        create_agent_template(self.agent_name,
                              self.agent_description,
                              instructions=self.instructions,
                              code_interpreter=True if "CodeInterpreter" in self.default_tools else None,
                              include_example_tool=False)

        # # create or append to init file
        path = self.shared_state.get("agency_path")
        folder_name = self.agent_name.lower().replace(" ", "_")
        class_name = self.agent_name.replace(" ", "").strip()
        if not os.path.isfile("__init__.py"):
            with open("__init__.py", "w") as f:
                f.write(f"from .{folder_name} import {class_name}")
        else:
            with open("__init__.py", "a") as f:
                f.write(f"\nfrom .{folder_name} import {class_name}")

        # add agent on second line to agency.py
        with open("agency.py", "r") as f:
            lines = f.readlines()
            lines.insert(1, f"from {self.agent_name} import {self.agent_name}\n")

        with open("agency.py", "w") as f:
            f.writelines(lines)

        os.chdir(self.shared_state.get("default_folder"))

        if "ceo" in self.agent_name.lower():
            return f"You can tell the user that the process of creating {self.agent_name} has been completed, because CEO agent does not need to utilizie any tools or APIs."

        return f"Agent template has been created for {self.agent_name}. Please now tell ToolCreator to create tools for this agent or OpenAPICreator to create API schemas, if this agent needs to utilize any tools or APIs. If this is unclear, please ask the user for more information."

    @model_validator(mode="after")
    def validate_tools(self):
        check_agency_path(self)

        for tool in self.default_tools:
            if tool not in allowed_tools:
                raise ValueError(f"Tool {tool} is not allowed. Allowed tools are: {allowed_tools}")
