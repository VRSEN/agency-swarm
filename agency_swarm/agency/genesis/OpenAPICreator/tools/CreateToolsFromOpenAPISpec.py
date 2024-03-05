import os

from pydantic import Field, field_validator, model_validator

from agency_swarm import BaseTool

import json

from agency_swarm.agency.genesis.util import check_agency_path, check_agent_path
from agency_swarm.tools import ToolFactory
from agency_swarm.util.openapi import validate_openapi_spec


class CreateToolsFromOpenAPISpec(BaseTool):
    """
    This tool creates a set of tools from an OpenAPI specification. Each method in the specification is converted to a separate tool.
    """
    agent_name: str = Field(
        ..., description="Name of the agent to create the API for. Must be an existing agent."
    )
    openapi_spec: str = Field(
        ..., description="OpenAPI specification for the tool to be created as a valid JSON string. Only the relevant "
                         "endpoints must be included. Responses are not required. Each method should contain "
                         "an operation id and a description. Do not truncate this schema. "
                         "It must be a full valid OpenAPI 3.1.0 specification.",
        examples=[
            '{\n  "openapi": "3.1.0",\n  "info": {\n    "title": "Get weather data",\n    "description": "Retrieves current weather data for a location.",\n    "version": "v1.0.0"\n  },\n  "servers": [\n    {\n      "url": "https://weather.example.com"\n    }\n  ],\n  "paths": {\n    "/location": {\n      "get": {\n        "description": "Get temperature for a specific location",\n        "operationId": "GetCurrentWeather",\n        "parameters": [\n          {\n            "name": "location",\n            "in": "query",\n            "description": "The city and state to retrieve the weather for",\n            "required": true,\n            "schema": {\n              "type": "string"\n            }\n          }\n        ],\n        "deprecated": false\n      }\n    }\n  },\n  "components": {\n    "schemas": {}\n  }\n}'])
    agency_name: str = Field(
        None, description="Name of the agency to create the tool for. Defaults to the agency currently being created."
    )

    def run(self):
        os.chdir(self.shared_state.get("agency_path"))

        os.chdir(self.agent_name)

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

            return "Successfully added OpenAPI Schema to " + self.shared_state.get("agent_name")
        finally:
            os.chdir(self.shared_state.get("default_folder"))

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

    @model_validator(mode="after")
    def validate_agent_name(self):
        check_agency_path(self)

        check_agent_path(self)

