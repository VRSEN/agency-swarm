import importlib.util
import inspect
import json
import os
import sys
from typing import Any, Dict, List, Type, Union

import jsonref
from jsonref import requests
from pydantic import create_model, Field

from .BaseTool import BaseTool
from ..util.schema import reference_schema


class ToolFactory:

    @staticmethod
    def from_langchain_tools(tools: List):
        """
        Converts a list of langchain tools into a list of BaseTools.
        :param tools: A list of langchain tools.
        :return: A list of BaseTools.
        """
        converted_tools = []
        for tool in tools:
            converted_tools.append(ToolFactory.from_langchain_tool(tool))

        return converted_tools

    @staticmethod
    def from_langchain_tool(tool):
        """
        Converts a langchain tool into a BaseTool.
        :param tool: A langchain tool.
        :return: A BaseTool.
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
    def from_openai_schema(schema: Dict[str, Any], callback: Any):
        """
        Converts an OpenAI schema into a BaseTool. Nested propoerties without refs are not supported yet.
        :param schema:
        :param callback:
        :return:
        """
        def resolve_ref(ref: str, defs: Dict[str, Any]) -> Any:
            # Extract the key from the reference
            key = ref.split('/')[-1]
            if key in defs:
                return defs[key]
            else:
                raise ValueError(f"Reference '{ref}' not found in definitions")

        def create_fields(schema: Dict[str, Any], type_mapping: Dict[str, Type[Any]], required_fields: List[str],
                          defs: Dict[str, Any]) -> Dict[str, Any]:
            fields = {}

            for prop, details in schema.items():
                alias = None
                if prop.startswith('_'):
                    alias = prop
                    prop = prop.lstrip('_')

                json_type = details['type'] if 'type' in details else 'any'

                if json_type in type_mapping:
                    field_type = type_mapping[json_type]
                    field_description = details.get('description', '')
                    is_required = prop in required_fields
                    field_default = ... if is_required else None

                    if json_type == 'array':
                        items_schema = details.get('items', {})
                        if 'type' in items_schema:
                            item_type = type_mapping[items_schema['type']]
                            field_type = List[item_type]
                        elif 'properties' in items_schema:  # Handling direct nested object in array
                            nested_properties = items_schema['properties']
                            nested_required = items_schema.get('required', [])
                            nested_model_name = items_schema.get('title', f"{prop}Item")
                            nested_fields = create_fields(nested_properties, type_mapping, nested_required, defs)
                            nested_model = create_model(nested_model_name, **nested_fields)
                            field_type = List[nested_model]
                        elif '$ref' in items_schema:
                            ref_model = resolve_ref(items_schema['$ref'], defs)
                            field_type = List[ref_model]
                        else:
                            raise ValueError("Array items must have a 'type', 'properties', or '$ref'")
                    elif json_type == 'object':
                        if 'properties' in details:
                            nested_properties = details['properties']
                            nested_required = details.get('required', [])
                            nested_model_name = details.get('title', f"{prop}Model")
                            nested_fields = create_fields(nested_properties, type_mapping, nested_required, defs)
                            field_type = create_model(nested_model_name, **nested_fields)
                        elif '$ref' in details:
                            ref_model = resolve_ref(details['$ref'], defs)
                            field_type = ref_model
                        else:
                            raise ValueError("Object must have 'properties' or '$ref'")

                    fields[prop] = (
                    field_type, Field(default=field_default, description=field_description, alias=alias))
                else:
                    raise ValueError(f"Unsupported type '{json_type}' for property '{prop}'")

            return fields

        type_mapping = {
            'string': str,
            'integer': int,
            'number': float,
            'boolean': bool,
            'array': List,
            'object': dict,
            'null': type(None),
            'any': Any,
        }

        schema = reference_schema(schema)

        name = schema['name']
        description = schema['description']
        properties = schema['parameters']['properties']
        required_fields = schema['parameters'].get('required', [])

        # Add definitions ($defs) to type_mapping
        defs = {k: create_model(k, **create_fields(v['properties'], type_mapping, v.get('required', []), {})) for k, v
                in schema['parameters'].get('$defs', {}).items()}
        type_mapping.update(defs)

        fields = create_fields(properties, type_mapping, required_fields, defs)

        # Dynamically creating the Pydantic model
        model = create_model(name, **fields)

        tool = type(name, (BaseTool, model), {
            "__doc__": description,
            "run": callback,
        })

        return tool

    @staticmethod
    def from_openapi_schema(schema: Union[str, dict], headers: Dict[str, str] = None, params: Dict[str, Any] = None):
        if isinstance(schema, dict):
            openapi_spec = schema
            openapi_spec = jsonref.JsonRef.replace_refs(openapi_spec)
        else:
            openapi_spec = jsonref.loads(schema)
        tools = []
        headers = headers or {}
        for path, methods in openapi_spec["paths"].items():
            for method, spec_with_ref in methods.items():
                def callback(self):
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
                    if method == "get":
                        return requests.get(url, params=parameters, headers=headers,
                                            json=self.model_dump().get('requestBody', None)
                                            ).json()
                    elif method == "post":
                        return requests.post(url,
                                             params=parameters,
                                             json=self.model_dump().get('requestBody', None),
                                             headers=headers
                                             ).json()
                    elif method == "put":
                        return requests.put(url,
                                            params=parameters,
                                            json=self.model_dump().get('requestBody', None),
                                            headers=headers
                                            ).json()
                    elif method == "delete":
                        return requests.delete(url,
                                               params=parameters,
                                               json=self.model_dump().get('requestBody', None),
                                               headers=headers
                                               ).json()

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
                    for param in spec_params:
                        if "schema" not in param and "type" in param:
                            param["schema"] = {"type": param["type"]}
                        param_properties[param["name"]] = param["schema"]
                        if "description" in param:
                            param_properties[param["name"]]["description"] = param["description"]
                        if "required" in param:
                            param_properties[param["name"]]["required"] = param["required"]
                        if "example" in param:
                            param_properties[param["name"]]["example"] = param["example"]
                    schema["properties"]["parameters"] = {
                        "type": "object",
                        "properties": param_properties,
                    }

                function = {
                    "name": function_name,
                    "description": desc,
                    "parameters": schema,
                }

                tools.append(ToolFactory.from_openai_schema(function, callback))

        return tools

    @staticmethod
    def from_file(file_path: str):
        """Dynamically imports a class from a Python file, ensuring BaseTool itself is not imported."""
        # Extract class name from file path (assuming class name matches file name without .py extension)
        class_name = os.path.basename(file_path)
        if class_name.endswith('.py'):
            class_name = class_name[:-3]  # Remove .py extension

        # Load the module from the given file path
        spec = importlib.util.spec_from_file_location(class_name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[class_name] = module
        spec.loader.exec_module(module)

        # Dynamically access the class based on the extracted class name
        if hasattr(module, class_name):
            tool = getattr(module, class_name)
        else:
            raise AttributeError(f"The class {class_name} was not found in {file_path}")

        return tool

    @staticmethod
    def get_openapi_schema(tools: List[Type[BaseTool]], url: str, title="Agent Tools",
                           description="A collection of tools."):
        """
        Generates an OpenAPI schema from a list of BaseTools.

            :param tools: BaseTools to generate the schema from.
            :param url: The base URL for the schema.
            :param title: The title of the schema.
            :param description: The description of the schema.

        :return: A JSON string representing the OpenAPI schema with all the tools combined as separate endpoints.
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
                    "parameters": [],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": openai_schema['parameters']
                            }
                        }
                    }
                }
            }

            schema['components']['schemas'].update(defs)

        schema = json.dumps(schema, indent=2).replace("#/$defs/", "#/components/schemas/")

        return schema
