import os


def create_agent_template(agent_name=None,
                          agent_description=None,
                          path="./",
                          instructions=None,
                          code_interpreter=False,
                          use_txt=False,
                          include_example_tool=True):
    if not agent_name:
        agent_name = input("Enter agent name: ")
    if not agent_description:
        agent_description = input("Enter agent description: ")

    class_name = agent_name.replace(" ", "").strip()
    folder_name = agent_name  # .lower().replace(" ", "_").strip()

    # create folder
    path = os.path.join(path, folder_name) + "/"
    if os.path.isdir(path):
        raise Exception("Folder already exists.")
    os.mkdir(path)

    # create agent file
    with open(path + folder_name + ".py", "w") as f:
        f.write(agent_template.format(
            class_name=class_name,
            agent_name=agent_name,
            agent_description=agent_description,
            ext="md" if not use_txt else "txt",
            code_interpreter="CodeInterpreter" if code_interpreter else "",
            code_interpreter_import="from agency_swarm.tools import CodeInterpreter" if code_interpreter else ""
        ))

    with open(path + "__init__.py", "w") as f:
        f.write(f"from .{folder_name} import {class_name}")

    # create instructions file
    instructions_path = "instructions.md" if not use_txt else "instructions.txt"
    with open(path + instructions_path, "w") as f:
        if instructions:
            f.write(instructions)
        else:
            f.write(f"# {agent_name} Instructions\n\n")

    # create files folder
    os.mkdir(path + "files")
    os.mkdir(path + "schemas")
    os.mkdir(path + "tools")

    # with open(path + "tools/" + "__init__.py", "w") as f:
    #     f.write("")

    if include_example_tool:
        with open(path + "tools/" + "ExampleTool.py", "w") as f:
            f.write(example_tool_template)

    print("Agent folder created successfully.")
    print(f"Import it with: from {folder_name} import {class_name}")


agent_template = """from agency_swarm.agents import Agent
{code_interpreter_import}

class {class_name}(Agent):
    def __init__(self):
        super().__init__(
            name="{agent_name}",
            description="{agent_description}",
            instructions="./instructions.{ext}",
            files_folder="./files",
            schemas_folder="./schemas",
            tools=[{code_interpreter}],
            tools_folder="./tools",
            temperature=0.3,
            max_prompt_tokens=25000,
        )
        
    def response_validator(self, message):
        return message
"""

example_tool_template = """from agency_swarm.tools import BaseTool
from pydantic import Field
import os

account_id = "MY_ACCOUNT_ID"
api_key = os.getenv("MY_API_KEY") # or access_token = os.getenv("MY_ACCESS_TOKEN")

class ExampleTool(BaseTool):
    \"\"\"
    A brief description of what the custom tool does.
    The docstring should clearly explain the tool's purpose and functionality.
    It will be used by the agent to determine when to use this tool.
    \"\"\"

    # Define the fields with descriptions using Pydantic Field
    example_field: str = Field(
        ..., description="Description of the example field, explaining its purpose and usage for the Agent."
    )

    def run(self):
        \"\"\"
        The implementation of the run method, where the tool's main functionality is executed.
        This method should utilize the fields defined above to perform the task.
        Docstring is not required for this method and will not be used by the agent.
        \"\"\"
        # Your custom tool logic goes here
        # do_something(self.example_field, api_key, account_id)

        # Return the result of the tool's operation as a string
        return "Result of ExampleTool operation"
"""
