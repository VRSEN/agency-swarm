import os

from pydantic import Field, field_validator

from agency_swarm import BaseTool

import json

from agency_swarm.tools import ToolFactory
from agency_swarm.util.openapi import validate_openapi_spec


class CreateToolsFromOpenAPISpec(BaseTool):
    """
    This tool creates a set of tools from an OpenAPI specification. Each method in the specification is converted to a separate tool.
    """
    agent_name: str = Field(
        ..., description="Name of the agent for whom the tools are being created. Cannot include special characters."
    )
    openapi_spec: str = Field(
        ..., description="OpenAPI specification for the tool to be created as a valid JSON string. Only the relevant "
                         "endpoints must be included. Responses are not required. Each method should contain "
                         "an operation id and a description. Must be full OpenAPI 3.1.0 specification.",
        examples=[
            '{\n  "openapi": "3.1.0",\n  "info": {\n    "title": "Get weather data",\n    "description": "Retrieves current weather data for a location.",\n    "version": "v1.0.0"\n  },\n  "servers": [\n    {\n      "url": "https://weather.example.com"\n    }\n  ],\n  "paths": {\n    "/location": {\n      "get": {\n        "description": "Get temperature for a specific location",\n        "operationId": "GetCurrentWeather",\n        "parameters": [\n          {\n            "name": "location",\n            "in": "query",\n            "description": "The city and state to retrieve the weather for",\n            "required": true,\n            "schema": {\n              "type": "string"\n            }\n          }\n        ],\n        "deprecated": false\n      }\n    }\n  },\n  "components": {\n    "schemas": {}\n  }\n}'])

    def run(self):
        try:
            try:
                tools = ToolFactory.from_openapi_schema(self.openapi_spec)
            except Exception as e:
                raise ValueError(f"Error creating tools from OpenAPI Spec: {e}")

            if len(tools) == 0:
                return "No tools created. Please check the OpenAPI specification."

            tool_names = [tool.__name__ for tool in tools]

            # save openapi spec
            folder_path = "./" + self.agent_name + "/"
            os.chdir(folder_path)

            api_name = json.loads(self.openapi_spec)["info"]["title"]

            api_name = api_name.replace("API", "Api").replace(" ", "")

            api_name = ''.join(['_' + i.lower() if i.isupper() else i for i in api_name]).lstrip('_')

            with open("schemas/" + api_name + ".json", "w") as f:
                f.write(self.openapi_spec)

            return "Successfully added OpenAPI Schema to agent."
        finally:
            os.chdir("../")

    @field_validator("openapi_spec", mode='before')
    @classmethod
    def validate_openapi_spec(cls, v):
        try:
            validate_openapi_spec(v)
        except json.JSONDecodeError as e:
            raise ValueError("Invalid JSON format:", e)
        except Exception as e:
            raise ValueError("Error validating OpenAPI schema:", e)
        return v

    @field_validator("agent_name", mode='before')
    @classmethod
    def validate_agent_name(cls, v):
        available_agents = os.listdir("./")
        available_agents = [agent for agent in available_agents if os.path.isdir(agent)]

        if not v.isalnum():
            raise ValueError(f"Agent name must be alphanumeric. Available agent names are: {available_agents}")

        if not os.path.exists(f"./{v}"):
            raise ValueError(f"Agent {v} does not exist. Available agents are: {available_agents}")

        return v
