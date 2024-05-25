from enum import Enum
import importlib.util
import inspect
import json
import os
import sys
from importlib import import_module
from typing import Any, Dict, List, Type, Union
import typing

import jsonref
from jsonref import requests
from pydantic import create_model, Field

from .BaseTool import BaseTool
from ..util.schema import dereference_schema, reference_schema


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
        def resolve_ref(ref: str, defs: Dict[str, Any]) -> Any:
            key = ref.split('/')[-1]
            if key in defs:
                print(f"Resolving ref '{ref}' to model '{key}'")
                return defs[key]
            else:
                raise ValueError(f"Reference '{ref}' not found in definitions")

        def create_fields(schema: Dict[str, Any], type_mapping: Dict[str, Type[Any]], required_fields: List[str], defs: Dict[str, Any], title=None) -> Dict[str, Any]:
            fields = {}

            if 'enum' in schema:
                enum_name = schema.get('title', 'Enum')
                enum_values = schema['enum']
                enum_type = Enum(enum_name, {value: value for value in enum_values})
                fields[title] = (enum_type, Field(default=None, description=schema.get('description', ''), title=title))
                return fields
            
            for prop, details in schema.items():
                alias = None
                if prop.startswith('_'):
                    alias = prop
                    prop = prop.lstrip('_')
                
                if 'type' in details:
                    json_type = details['type']
                elif 'anyOf' in details:
                    json_type = 'anyOf'
                else:
                    json_type = 'any'
                print(f"Creating field '{prop}' of type '{json_type}'")

                if json_type in type_mapping:
                    field_type = type_mapping[json_type]
                    field_description = details.get('description', '')
                    print('Field description: ', field_description)
                    is_required = prop in required_fields
                    field_default = ... if is_required else None
                    if 'default' in details and details['default'] in type_mapping:
                        field_default = details['default']

                    if json_type == 'array':
                        items_schema = details.get('items', {})
                        if 'type' in items_schema:
                            item_type = type_mapping[items_schema['type']]
                            if items_schema['type'] == 'object':
                                nested_properties = items_schema.get('properties', {})
                                nested_required = items_schema.get('required', [])
                                nested_model_name = items_schema.get('title', prop)
                                nested_fields = create_fields(nested_properties, type_mapping, nested_required, defs)
                                nested_model = create_model(nested_model_name, **nested_fields)
                                field_type = List[nested_model]
                                print(f"Field '{prop}' is an array of '{items_schema['type']}'")
                            else:
                                field_type = List[item_type]    
                                print(f"Field '{prop}' is an array of '{items_schema['type']}'")
                        elif 'properties' in items_schema:
                            nested_properties = items_schema['properties']
                            nested_required = items_schema.get('required', [])
                            nested_model_name = items_schema.get('title', prop)
                            nested_fields = create_fields(nested_properties, type_mapping, nested_required, defs)
                            nested_model = create_model(nested_model_name, **nested_fields)
                            field_type = List[nested_model]
                            print(f"Field '{prop}' is an array of nested objects '{nested_model_name}'")
                        elif '$ref' in items_schema:
                            ref_model = resolve_ref(items_schema['$ref'], defs)
                            field_type = List[ref_model]
                            print(f"Field '{prop}' is an array of references '{items_schema['$ref']}'")
                        else:
                            raise ValueError("Array items must have a 'type', 'properties', or '$ref'")
                    elif json_type == 'object':
                        if 'properties' in details:
                            nested_properties = details['properties']
                            nested_required = details.get('required', [])
                            nested_model_name = details.get('title', prop)
                            nested_fields = create_fields(nested_properties, type_mapping, nested_required, defs)
                            field_type = create_model(nested_model_name, **nested_fields)
                            print(f"Field '{prop}' is a nested object '{nested_model_name}'")
                        elif '$ref' in details:
                            ref_model = resolve_ref(details['$ref'], defs)
                            field_type = ref_model
                            print(f"Field '{prop}' is a reference '{details['$ref']}'")
                        else:
                            raise ValueError("Object must have 'properties' or '$ref'")

                    fields[prop] = (field_type, Field(default=field_default, description=field_description, alias=alias, title=title))
                    print('Field created: ', fields[prop])
                elif 'anyOf' in details:
                    field_types = []
                    for item in details['anyOf']:
                        if 'items' in item:
                            item = item['items']
                            nested_properties = item.get('properties', {})
                            nested_required = item.get('required', [])
                            nested_model_name = item.get('title', prop)
                            nested_fields = create_fields(nested_properties, type_mapping, nested_required, defs)
                            nested_model = create_model(nested_model_name, **nested_fields)
                            field_types.append(nested_model)
                        elif 'type' in item:
                            field_types.append(type_mapping[item['type']])
                    field_type = Union[tuple(field_types)]  # type: ignore
                    field_description = details.get('description', '')
                    is_required = prop in required_fields
                    field_default = ... if is_required else None
                    if 'default' in details and details['default'] in type_mapping:
                        field_default = details['default']
                    fields[prop] = (field_type, Field(default=field_default, description=field_description, alias=alias, title=title))
                    print(f"Field '{prop}' is an anyOf of '{field_types}'")
                elif 'allOf' in details:
                    field_types = []
                    for item in details['allOf']:
                        if 'items' in item:
                            item = item['items']
                            nested_properties = item.get('properties', {})
                            nested_required = item.get('required', [])
                            nested_model_name = item.get('title', prop)
                            nested_fields = create_fields(nested_properties, type_mapping, nested_required, defs)
                            nested_model = create_model(nested_model_name, **nested_fields)
                            field_types.append(nested_model)
                        elif 'type' in item:
                            field_types.append(type_mapping[item['type']])
                    field_type = typing.All[tuple(field_types)]
                    field_description = details.get('description', '')
                    is_required = prop in required_fields
                    field_default = ... if is_required else None
                    if 'default' in details and details['default'] in type_mapping:
                        field_default = details['default']
                    fields[prop] = (field_type, Field(default=field_default, description=field_description, alias=alias, title=title))
                    print(f"Field '{prop}' is an allOf of '{field_types}'")
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
            "enum": Enum,
        }

        name = schema['name']
        description = schema['description']
        properties = schema['parameters']['properties']
        required_fields = schema['parameters'].get('required', [])

        schema = dereference_schema(schema)

        print("Schema dereferenced: ", json.dumps(schema, indent=4))
        
        defs = {k: create_model(k, **create_fields(v.get('properties', v), type_mapping, v.get('required', []), {}, v.get('title', k))) for k, v in schema['parameters'].get('$defs', {}).items()}
        type_mapping.update(defs)

        print("Definitions created: ", defs)

        print("Creating fields for parameters...")
        fields = create_fields(properties, type_mapping, required_fields, defs)
        print("Fields created: ", fields)

        # Create the Pydantic model using the new method
        print("Creating the final model using final method...")
        model = create_model(name, __config__=type('Config', (), {'arbitrary_types_allowed': True}), **fields)
        print("Model created: ", model)

        # Create a new tool class dynamically
        tool_class = type(name, (BaseTool, model), {
            "__doc__": description,
            "run": callback,
        })

        print("Tool created: ", tool_class)
        print("Tool annotations: ", tool_class.__annotations__)
        print("Tool fields: ", tool_class.__fields__)
        
        # Check where the empty dictionary {} is coming from
        print("GeneratedTool requestBody attributes: ", getattr(tool_class, 'requestBody', {}))

        return tool_class

    @staticmethod
    def from_openapi_schema(schema: Union[str, dict], headers: Dict[str, str] = None, params: Dict[str, Any] = None) \
            -> List[Type[BaseTool]]:
        """
        Converts an OpenAPI schema into a list of BaseTools.

        Parameters:
            schema: The OpenAPI schema to convert.
            headers: The headers to use for requests.
            params: The parameters to use for requests.

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
                        if "examples" in param:
                            param_properties[param["name"]]["examples"] = param["examples"]
                    schema["properties"]["parameters"] = {
                        "type": "object",
                        "properties": param_properties,
                    }

                function = {
                    "name": function_name,
                    "description": desc,
                    "parameters": schema,
                }

                print("before function ", json.dumps(function, indent=4))

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
