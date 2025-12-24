"""Create agent template utility for Agency Swarm CLI."""

import re
from pathlib import Path

from .model_utils import is_reasoning_model


def create_agent_template(
    agent_name=None,
    agent_description=None,
    model="gpt-5.2",
    reasoning=None,
    max_tokens=None,
    temperature=None,
    path="./",
    instructions=None,
    use_txt=False,
    include_example_tool=True,
) -> bool:
    """Create an agent template with the specified structure.

    Returns
    -------
    bool
        ``True`` when the template is created successfully, ``False`` when
        validation fails before any files are generated.
    """
    if not agent_name:
        agent_name = input("Enter agent name: ")

    # Validate inputs
    try:
        _validate_agent_name(agent_name)
        _validate_temperature(temperature)
    except ValueError as e:
        print(f"\033[91mERROR: {e}\033[0m")
        return False

    # Set appropriate defaults and validate compatibility
    if is_reasoning_model(model):
        if temperature is not None:
            print(f"\033[91mERROR: Reasoning models (like {model}) do not support the temperature parameter.\033[0m")
            print("\033[91mTemperature parameter will be ignored.\033[0m")
        temperature = None  # Always None for reasoning models
    else:
        # Non-reasoning model - set default temperature if not provided
        if temperature is None:
            temperature = 0.3

        if reasoning:
            print(f"\033[91mERROR: Non-reasoning models (like {model}) do not support the reasoning parameter.\033[0m")
            print("\033[91mReasoning parameter will be ignored.\033[0m")
        reasoning = None

    # Normalize agent name for folder/file names (lowercase with underscores).
    # Dots are common in version-like agent names (e.g., "Agent 1.2"). Dots are not valid
    # in Python module names, so normalize them to underscores.
    normalized_name = agent_name.replace(".", "_")
    folder_name = normalized_name.lower().replace(" ", "_").replace("-", "_")
    class_name = normalized_name.replace(" ", "").replace("-", "").strip()

    # Create folder using pathlib for cross-platform compatibility
    base_path = Path(path)
    agent_path = base_path / folder_name

    if agent_path.exists():
        raise FileExistsError("Folder already exists.")

    agent_path.mkdir(parents=True, exist_ok=False)

    # create agent file
    # Build conditional template parts
    reasoning_import = ""
    reasoning_line = ""
    if reasoning:
        reasoning_import = "\nfrom openai.types.shared import Reasoning"
        # GPT-5 models support summary parameter in Reasoning
        if model.startswith("gpt-5"):
            reasoning_line = f'\n        reasoning=Reasoning(effort="{reasoning}", summary="auto"),'
        else:
            reasoning_line = f'\n        reasoning=Reasoning(effort="{reasoning}"),'

    max_tokens_line = ""
    if max_tokens:
        max_tokens_line = f"\n        max_completion_tokens={max_tokens},"

    temperature_line = ""
    if temperature is not None:
        temperature_line = f"\n        temperature={temperature},"

    description_line = ""
    if agent_description:
        description_line = f'\n    description="{agent_description}",'

    with open(agent_path / f"{folder_name}.py", "w") as f:
        f.write(
            agent_template.format(
                folder_name=folder_name,
                class_name=class_name,
                agent_name=agent_name,
                description_line=description_line,
                model=model,
                reasoning_import=reasoning_import,
                reasoning_line=reasoning_line,
                max_tokens_line=max_tokens_line,
                temperature_line=temperature_line,
                ext="md" if not use_txt else "txt",
            )
        )

    with open(agent_path / "__init__.py", "w") as f:
        f.write(f"from .{folder_name} import {folder_name}")

    # create instructions file
    instructions_path = "instructions.md" if not use_txt else "instructions.txt"
    with open(agent_path / instructions_path, "w") as f:
        if instructions:
            f.write(instructions)
        else:
            # Use structured template
            role_description = (
                agent_description.replace('"', "'")
                if agent_description
                else "**[insert role, e.g., 'a helpful expert' or 'a creative storyteller'.]**"
            )
            content = f"""# Role

You are {role_description}

# Goals

- **[Insert high level goals for the business (e.g., if you are building a report generator agent - increase sales by 10%)]**

# Process

## [Task Name]

**[Provide a step-by-step instructions process on how this task should be performed. Use a numbered list.]**

[...repeat for each task]

# Output Format

- **[Best suited output format for the agent (e.g., "respond concisely and use simple language") or examples.]**

# Additional Notes

- **[Specify any additional notes here, if any. Use bullet points if needed.]**
"""  # noqa: E501
            f.write(content)

    # create folders
    (agent_path / "files").mkdir()
    (agent_path / "tools").mkdir()

    # create tools __init__.py
    with open(agent_path / "tools" / "__init__.py", "w") as f:
        f.write('"""Tools for the agent."""\n')

    if include_example_tool:
        with open(agent_path / "tools" / "ExampleTool.py", "w") as f:
            f.write(example_tool_template)

    print("Agent folder created successfully.")
    print(f"Created at: {agent_path.absolute()}")
    print(f"Import it with: from {folder_name} import {folder_name}")

    return True


def _validate_agent_name(name: str) -> None:
    """Validate agent name for invalid characters and patterns."""
    if not name or not name.strip():
        raise ValueError("Agent name cannot be empty")

    # Check for invalid characters that would cause file system issues
    invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
    if re.search(invalid_chars, name):
        raise ValueError(f"Agent name contains invalid characters: {name}")


def _validate_temperature(temperature: float | None) -> None:
    """Validate temperature parameter range."""
    if temperature is not None:
        if not isinstance(temperature, int | float):
            raise ValueError("Temperature must be a number")
        if temperature < 0.0 or temperature > 2.0:
            raise ValueError("Temperature must be between 0.0 and 2.0")


agent_template = """from agency_swarm import Agent, ModelSettings{reasoning_import}


{folder_name} = Agent(
    name="{agent_name}",{description_line}
    instructions="./instructions.{ext}",
    files_folder="./files",
    tools_folder="./tools",
    model="{model}",
    model_settings=ModelSettings({temperature_line}{max_tokens_line}{reasoning_line}
    ),
)
"""

# Updated example tool template for v1.x
example_tool_template = """from agency_swarm.tools import BaseTool
from pydantic import Field
import os
from dotenv import load_dotenv

load_dotenv()

# Define constants at module level
account_id = "MY_ACCOUNT_ID"
api_key = os.getenv("MY_API_KEY")  # or access_token = os.getenv("MY_ACCESS_TOKEN")


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
        \"\"\"
        # Your custom tool logic goes here
        # Example:
        # do_something(self.example_field, api_key, account_id)

        # Return the result of the tool's operation as a string
        return f"Result of ExampleTool operation with {self.example_field}"


if __name__ == "__main__":
    tool = ExampleTool(example_field="test value")
    print(tool.run())
"""
