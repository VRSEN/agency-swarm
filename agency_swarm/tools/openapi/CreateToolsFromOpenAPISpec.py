import os

from openapi_spec_validator.validation.exceptions import OpenAPIValidationError
from pydantic import Field, field_validator

from agency_swarm import BaseTool

from openapi_spec_validator import validate
import json

from agency_swarm.tools import ToolFactory


class CreateToolsFromOpenAPISpec(BaseTool):
    """
    This tool creates a set of tools from an OpenAPI specification. Each method in the specification is converted to a separate tool.
    """
    agent_name: str = Field(
        ..., description="Name of the agent for whom the tools are being created. Cannot include special characters."
    )
    openapi_spec: str = Field(
        ..., description="OpenAPI specification for the tool to be created as a valid JSON string. Only the relevant endpoints should be included. Responses field is not required.")

    def run(self):
        try:
            tools = ToolFactory.from_openapi_schema(self.openapi_spec)
        except Exception as e:
            raise ValueError(f"Error creating tools: {e}")

        if len(tools) == 0:
            return "No tools created. Please check the OpenAPI specification."

        tool_names = [tool.name for tool in tools]

        # save openapi spec
        folder_path = "./" + self.agent_name + "/"
        os.chdir(folder_path)

        # check if openapi_spec.json exists
        i = 1
        while os.path.exists(f"openapi_spec_{i}.json"):
            i += 1

        with open(f"openapi_spec_{i}.json", "w") as f:
            f.write(self.openapi_spec)

        with open("tools.py", "r") as f:
            lines = f.readlines()

        with open("tools.py", "w") as f:
            f.write("from agency_swarm.tools import ToolFactory")
            f.write("\n\n")
            # append reading openapi spec
            f.write(f"with open('openapi_spec_{i}.json', 'r') as f:")
            f.write("\n")
            f.write(f"    spec_{i} = json.load(f)")
            f.writelines(lines)

        with open("tools.py", "a") as f:
            f.write("\n\n")
            f.write(f"tools{i} = ToolFactory.from_openapi_schema(spec_{i})")
            f.write("\n\n")

        os.chdir("../")

        return f"Tool(s) created: {tool_names}"


    @field_validator("openapi_spec", mode='before')
    @classmethod
    def validate_openapi_spec(cls, v):
        try:
            spec = json.loads(v)
            for path, path_item in spec.get('paths', {}).items():
                for operation in path_item.values():
                    if 'responses' not in operation:
                        operation['responses'] = {'default': {'description': 'Default response'}}
            validate(spec)
        except OpenAPIValidationError as e:
            raise ValueError("Validation error in OpenAPI schema:", e)
        except json.JSONDecodeError as e:
            raise ValueError("Invalid JSON format:", e)
        return v

    @field_validator("agent_name", mode='before')
    @classmethod
    def validate_agent_name(cls, v):
        available_agents = os.listdir("./")
        available_agents = [agent for agent in available_agents if os.path.isdir(agent)]

        if not v.isalnum():
            raise ValueError("Agent name must be alphanumeric. Available agent names are: {available_agents}")

        if not os.path.exists(f"./{v}"):
            raise ValueError(f"Agent {v} does not exist. Available agents are: {available_agents}")

        return v