import inspect
import json
import os
import sys
from importlib import import_module
from typing import Any, Dict, List, Type, Union

import jsonref
from jsonref import requests
from pydantic import create_model, Field

from .BaseTool import BaseTool
from ..util.schema import dereference_schema, reference_schema

from datamodel_code_generator import DataModelType, PythonVersion
from datamodel_code_generator.model import get_data_model_types
from datamodel_code_generator.parser.jsonschema import JsonSchemaParser

import httpx

class ToolFactory:

    @staticmethod
    def from_langchain_tools(tools: List) -> List[Type[BaseTool]]:
        """
        Converts a list of langchain tools into a list of BaseTools.

        Parameters:
            tools: The langchain tools to convert.

        Returns:
            A list of BaseTools.
        """
        converted_tools = []
        for tool in tools:
            converted_tools.append(ToolFactory.from_langchain_tool(tool))

        return converted_tools

    @staticmethod
    def from_langchain_tool(tool) -> Type[BaseTool]:
        """
        Converts a langchain tool into a BaseTool.

        Parameters:
            tool: The langchain tool to convert.

        Returns:
            A BaseTool.
        """
        try:
            from langchain.tools import format_tool_to_openai_function
        except ImportError:
            raise ImportError("You must install langchain to use this method.")

        if inspect.isclass(tool):
            tool = tool()

        def callback(self):
            tool_input = self.model_dump()
            try:
                return tool.run(tool_input)
            except TypeError:
                if len(tool_input) == 1:
                    return tool.run(list(tool_input.values())[0])
                else:
                    raise TypeError(f"Error parsing input for tool '{tool.__class__.__name__}' Please open an issue "
                                    f"on github.")

        return ToolFactory.from_openai_schema(
            format_tool_to_openai_function(tool),
            callback
        )


    @staticmethod
    def from_openai_schema(schema: Dict[str, Any], callback: Any) -> Type[BaseTool]:
        """
        Converts an OpenAI schema into a BaseTool.

        Parameters:
            schema: The OpenAI schema to convert.
            callback: The function to run when the tool is called.

        Returns:
            A BaseTool.
        """
        data_model_types = get_data_model_types(
            DataModelType.PydanticV2BaseModel,
            target_python_version=PythonVersion.PY_37
        )

        parser = JsonSchemaParser(
            json.dumps(schema['parameters']),
            data_model_type=data_model_types.data_model,
            data_model_root_type=data_model_types.root_model,
            data_model_field_type=data_model_types.field_model,
            data_type_manager_type=data_model_types.data_type_manager,
            dump_resolve_reference_action=data_model_types.dump_resolve_reference_action,
            use_schema_description=True,
            validation=False,
            class_name='Model',
            # custom_template_dir=Path('/Users/vrsen/Projects/agency-swarm/agency-swarm/agency_swarm/tools/data_schema_templates')
        )

        result = parser.parse()

        # # Execute the result to extract the model
        exec_globals = {}
        exec(result, exec_globals)
        model = exec_globals.get('Model')

        if not model:
            raise ValueError(f"Could not extract model from schema {schema['name']}")
        
        class ToolConfig:
            strict: bool = schema.get("strict", False)
        
        tool = type(schema['name'], (BaseTool, model), {
            "__doc__": schema.get('description', ""),
            "run": callback,
        })

        tool.ToolConfig = ToolConfig

        return tool

    @staticmethod
    def from_openapi_schema(schema: Union[str, dict], headers: Dict[str, str] = None, params: Dict[str, Any] = None, strict: bool = False) \
            -> List[Type[BaseTool]]:
        """
        Converts an OpenAPI schema into a list of BaseTools.

        Parameters:
            schema: The OpenAPI schema to convert.
            headers: The headers to use for requests.
            params: The parameters to use for requests.
            strict: Whether to use strict OpenAI mode.
        Returns:
            A list of BaseTools.
        """
        if isinstance(schema, dict):
            openapi_spec = schema
            openapi_spec = jsonref.JsonRef.replace_refs(openapi_spec)
        else:
            openapi_spec = jsonref.loads(schema)
        tools = []
        headers = headers or {}
        headers = {k: v for k, v in headers.items() if v is not None}
        for path, methods in openapi_spec["paths"].items():
            for method, spec_with_ref in methods.items():
                async def callback(self):
                    url = openapi_spec["servers"][0]["url"] + path
                    parameters = self.model_dump().get('parameters', {})
                    # replace all parameters in url
                    for param, value in parameters.items():
                        if "{" + str(param) + "}" in url:
                            url = url.replace(f"{{{param}}}", str(value))
                            parameters[param] = None
                    url = url.rstrip("/")
                    parameters = {k: v for k, v in parameters.items() if v is not None}
                    parameters = {**parameters, **params} if params else parameters
                    async with httpx.AsyncClient(timeout=90) as client:  # Set custom read timeout to 10 seconds
                        if method == "get":
                            response = await client.get(url, params=parameters, headers=headers)
                        elif method == "post":
                            response = await client.post(url,
                                                         params=parameters,
                                                         json=self.model_dump().get('requestBody', None),
                                                         headers=headers)
                        elif method == "put":
                            response = await client.put(url,
                                                        params=parameters,
                                                        json=self.model_dump().get('requestBody', None),
                                                        headers=headers)
                        elif method == "delete":
                            response = await client.delete(url,
                                                           params=parameters,
                                                           json=self.model_dump().get('requestBody', None),
                                                           headers=headers)
                        return response.json()

                # 1. Resolve JSON references.
                spec = jsonref.replace_refs(spec_with_ref)

                # 2. Extract a name for the functions.
                function_name = spec.get("operationId")

                # 3. Extract a description and parameters.
                desc = spec.get("description") or spec.get("summary", "")

                schema = {"type": "object", "properties": {}}

                req_body = (
                    spec.get("requestBody", {})
                    .get("content", {})
                    .get("application/json", {})
                    .get("schema")
                )
                if req_body:
                    schema["properties"]["requestBody"] = req_body

                spec_params = spec.get("parameters", [])
                if spec_params:
                    param_properties = {}
                    required_params = []
                    for param in spec_params:
                        if "schema" not in param and "type" in param:
                            param["schema"] = {"type": param["type"]}
                        param_properties[param["name"]] = param["schema"]
                        if "description" in param:
                            param_properties[param["name"]]["description"] = param["description"]
                        if "required" in param and param["required"]:
                            required_params.append(param["name"])
                        if "example" in param:
                            param_properties[param["name"]]["example"] = param["example"]
                        if "examples" in param:
                            param_properties[param["name"]]["examples"] = param["examples"]
                    
                    schema["properties"]["parameters"] = {
                        "type": "object",
                        "properties": param_properties,
                        "required": required_params
                    }

                function = {
                    "name": function_name,
                    "description": desc,
                    "parameters": schema,
                    "strict": strict
                }

                tools.append(ToolFactory.from_openai_schema(function, callback))

        return tools
    
    @staticmethod
    def from_file(file_path: str) -> Type[BaseTool]:
        """Dynamically imports a BaseTool class from a Python file within a package structure.

        Parameters:
            file_path: The file path to the Python file containing the BaseTool class.

        Returns:
            The imported BaseTool class.
        """
        file_path = os.path.relpath(file_path)
        # Normalize the file path to be absolute and extract components
        directory, file_name = os.path.split(file_path)
        import_path = os.path.splitext(file_path)[0].replace(os.sep, ".")
        class_name = os.path.splitext(file_name)[0]

        exec_globals = globals()
        
        # importing from agency_swarm package
        if "agency_swarm" in import_path:
            import_path = import_path.lstrip(".")
            exec(f"from {import_path} import {class_name}", exec_globals)
        # importing from current working directory
        else:
            current_working_directory = os.getcwd()
            sys.path.append(current_working_directory)
            exec(f"from {import_path} import {class_name}", exec_globals)

        

        imported_class = exec_globals.get(class_name)
        if not imported_class:
            raise ImportError(f"Could not import {class_name} from {import_path}")

        # Check if the imported class is a subclass of BaseTool
        if not issubclass(imported_class, BaseTool):
            raise TypeError(f"Class {class_name} must be a subclass of BaseTool")

        return imported_class

    @staticmethod
    def get_openapi_schema(tools: List[Type[BaseTool]], url: str, title="Agent Tools",
                           description="A collection of tools.") -> str:
        """
        Generates an OpenAPI schema from a list of BaseTools.

        Parameters:
            tools: BaseTools to generate the schema from.
            url: The base URL for the schema.
            title: The title of the schema.
            description: The description of the schema.

        Returns:
            A JSON string representing the OpenAPI schema with all the tools combined as separate endpoints.
        """
        schema = {
            "openapi": "3.1.0",
            "info": {
                "title": title,
                "description": description,
                "version": "v1.0.0"
            },
            "servers": [
                {
                    "url": url,
                }
            ],
            "paths": {},
            "components": {
                "schemas": {},
                "securitySchemes": {
                    "apiKey": {
                        "type": "apiKey"
                    }
                }
            },
        }

        for tool in tools:
            if not issubclass(tool, BaseTool):
                continue

            openai_schema = tool.openai_schema
            defs = {}
            if '$defs' in openai_schema['parameters']:
                defs = openai_schema['parameters']['$defs']
                del openai_schema['parameters']['$defs']

            schema['paths']["/" + openai_schema['name']] = {
                "post": {
                    "description": openai_schema['description'],
                    "operationId": openai_schema['name'],
                    "x-openai-isConsequential": False,
                    "parameters": [],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": openai_schema['parameters']
                            }
                        }
                    },
                }
            }

            schema['components']['schemas'].update(defs)

        schema = json.dumps(schema, indent=2).replace("#/$defs/", "#/components/schemas/")

        return schema