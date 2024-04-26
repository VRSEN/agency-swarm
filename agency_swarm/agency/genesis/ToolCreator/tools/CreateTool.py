import os
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from agency_swarm import get_openai_client
from agency_swarm.agency.genesis.util import check_agency_path
from agency_swarm.tools import BaseTool

prompt = """# Agency Swarm Overview

Agency Swarm started as a desire and effort of Arsenii Shatokhin (aka VRSEN) to fully automate his AI Agency with AI. By building this framework, we aim to simplify the agent creation process and enable anyone to create a collaborative swarm of agents (Agencies), each with distinct roles and capabilities. 

# ToolCreator Agent Instructions for Agency Swarm Framework

As a ToolCreator Agent within the Agency Swarm framework, your mission is to develop tools that enhance the capabilities of other agents. These tools are pivotal for enabling agents to communicate, collaborate, and efficiently achieve their collective objectives. Below are detailed instructions to guide you through the process of creating tools, ensuring they are both functional and align with the framework's standards.

### Tool Creation Guide

When creating a tool, you are essentially defining a new class that extends `BaseTool`. This process involves several key steps, outlined below.

#### 1. Import Necessary Modules

Start by importing `BaseTool` from `agency_swarm.tools` and `Field` from `pydantic`. These imports will serve as the foundation for your custom tool class. Import any additional packages necessary to implement the tool's logic.

#### 2. Define Your Tool Class

Create a new class that inherits from `BaseTool`. This class will encapsulate the functionality of your tool. `BaseTool` class inherits from the Pydantic's `BaseModel` class.

#### 3. Specify Tool Fields

Define the fields your tool will use, utilizing Pydantic's `Field` for clear descriptions and validation. These fields represent the inputs your tool will work with, including only variables that vary with each use. Define any constant variables like api keys globally.

#### 4. Implement the `run` Method

The `run` method is where your tool's logic is executed. Use the fields defined earlier to perform the tool's intended task. It must contain the actual fully functional correct python code. It can utilize various python packages, previously imported in step 1. Do not include any placeholders or hypothetical examples in the code.

### Example of a Custom Tool

```python
from agency_swarm.tools import BaseTool
from pydantic import Field
import os

account_id = "MY_ACCOUNT_ID"
api_key = os.getenv("MY_API_KEY") # or access_token = os.getenv("MY_ACCESS_TOKEN")

class MyCustomTool(BaseTool):
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
        \"\"\"
        # Your custom tool logic goes here
        # Example: 
        # do_something(self.example_field, api_key, account_id)

        # Return the result of the tool's operation as a string
        return "Result of MyCustomTool operation"
```

To share state between 2 or more tools, you can use the `shared_state` attribute of the tool. It is a dictionary that can be used to store and retrieve values across different tools. This can be useful for passing information between tools or agents. Here is an example of how to use the `shared_state`:

```python
class MyCustomTool(BaseTool):
    def run(self):
        # Access the shared state
        value = self.shared_state.get("key")
        
        # Update the shared state
        self.shared_state.set("key", "value")
        
        return "Result of MyCustomTool operation"
        
# Access shared state in another tool
class AnotherTool(BaseTool):
    def run(self):
        # Access the shared state
        value = self.shared_state.get("key")
        
        return "Result of AnotherTool operation"
```

This is useful to pass information between tools or agents or to verify the state of the system.  

Remember, you must output the resulting python tool code as a whole, so the user can just copy and paste it into his program. Each tool code snippet must be ready to use. It must not contain any placeholders or hypothetical examples."""

history = [
            {
                "role": "system",
                "content": prompt
            },
        ]


class CreateTool(BaseTool):
    """This tool creates other custom tools for the agent, based on your requirements and details."""
    agent_name: str = Field(
        ..., description="Name of the agent to create the tool for."
    )
    tool_name: str = Field(..., description="Name of the tool class in camel case.", examples=["ExampleTool"])
    requirements: str = Field(
        ...,
        description="The comprehensive requirements explaning the primary functionality of the tool. It must not contain any code or implementation details."
    )
    details: str = Field(
        None, description="Additional details or error messages, class, function, and variable names."
    )
    mode: Literal["write", "modify"] = Field(
        ..., description="The mode of operation for the tool. 'write' is used to create a new tool or overwrite an existing one. 'modify' is used to modify an existing tool."
    )
    agency_name: str = Field(
        None, description="Name of the agency to create the tool for. Defaults to the agency currently being created."
    )
    one_call_at_a_time: bool = True

    def run(self):
        if self.agency_name:
            os.chdir("./" + self.agency_name)
        else:
            os.chdir(self.shared_state.get("agency_path"))
        os.chdir(self.agent_name)

        client = get_openai_client()

        if self.mode == "write":
            message = f"Please create a '{self.tool_name}' tool that meets the following requirements: '{self.requirements}'.\n\nThe tool class must be named '{self.tool_name}'."
        else:
            message = f"Please rewrite a '{self.tool_name}' according to the following requirements: '{self.requirements}'.\n\nThe tool class must be named '{self.tool_name}'."

        if self.details:
            message += f"\nAdditional Details: {self.details}"

        if self.mode == "modify":
            message += f"\nThe existing file content is as follows:"

            try:
                with open("./tools/" + self.tool_name + ".py", 'r') as file:
                    prev_content = file.read()
                    message += f"\n\n```{prev_content}```"
            except Exception as e:
                os.chdir(self.shared_state.get("default_folder"))
                return f'Error reading {self.tool_name}: {e}'

        history.append({
                "role": "user",
                "content": message
            })

        messages = history.copy()

        # use the last 5 messages
        messages = messages[-5:]

        # add system message upfront
        messages.insert(0, history[0])

        n = 0
        error_message = ""
        while n < 3:
            resp = client.chat.completions.create(
                messages=messages,
                model="gpt-4-turbo",
                temperature=0,
            )

            content = resp.choices[0].message.content

            messages.append(
                {
                    "role": "assistant",
                    "content": content
                }
            )

            pattern = r"```(?:[a-zA-Z]+\n)?(.*?)```"
            match = re.findall(pattern, content, re.DOTALL)
            if match:
                code = match[-1].strip()
                history.append(
                    {
                        "role": "assistant",
                        "content": content
                    }
                )

                break
            else:
                messages.append(
                    {
                        "role": "user",
                        "content": f"Error: Could not find the code block in the response. Please try again."
                    }
                )

            n += 1

        if n == 3 or not code:
            history.append(
                {
                    "role": "assistant",
                    "content": content
                }
            )
            history.append(
                {
                    "role": "user",
                    "content": error_message
                }
            )
            os.chdir(self.shared_state.get("default_folder"))
            return "Error: Could not generate a valid file: " + error_message

        try:
            with open("./tools/" + self.tool_name + ".py", "w") as file:
                file.write(code)

            os.chdir(self.shared_state.get("default_folder"))
            return f'{content}\n\nPlease make sure to now test this tool if possible.'
        except Exception as e:
            os.chdir(self.shared_state.get("default_folder"))
            return f'Error writing to file: {e}'

    @field_validator("requirements", mode="after")
    @classmethod
    def validate_requirements(cls, v):
        if "placeholder" in v:
            raise ValueError("Requirements contain placeholders. "
                             "Please never user placeholders. Instead, implement only the code that you are confident about.")

        # check if code is included in requirements
        pattern = r'(```)((.*\n){5,})(```)'
        if re.search(pattern, v):
            raise ValueError(
                "Requirements contain a code snippet. Please never include code snippets in requirements. "
                "Requirements must be a description of the complete file to be written. You can include specific class, function, and variable names, but not the actual code."
            )

        return v

    @field_validator("details", mode="after")
    @classmethod
    def validate_details(cls, v):
        if len(v) == 0:
            raise ValueError("Details are required. Remember this tool does not have access to other files. Please provide additional details like relevant documentation, error messages, or class, function, and variable names from other files that this file depends on.")
        return v

    @model_validator(mode="after")
    def validate_agency_name(self):
        if not self.agent_name and not self.shared_state.get("agent_name"):
            raise ValueError("Please provide agent name.")

        check_agency_path(self)


if __name__ == "__main__":
    tool = CreateTool(
        requirements="Write a program that takes a list of integers as input and returns the sum of all the integers in the list.",
        mode="write",
        file_path="test.py",
    )
    print(tool.run())