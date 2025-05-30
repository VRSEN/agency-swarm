import inspect
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import logging
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Tuple, Type, Union

import httpx
import jsonref
from datamodel_code_generator import DataModelType, PythonVersion
from datamodel_code_generator.model import get_data_model_types
from datamodel_code_generator.parser.jsonschema import JsonSchemaParser

from .BaseTool import BaseTool

logger = logging.getLogger(__name__)
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
            from langchain_community.tools import format_tool_to_openai_function
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
                    raise TypeError(
                        f"Error parsing input for tool '{tool.__class__.__name__}' Please open an issue "
                        f"on github."
                    )

        return ToolFactory.from_openai_schema(
            format_tool_to_openai_function(tool), callback
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
            target_python_version=PythonVersion.PY_310,
        )

        parser = JsonSchemaParser(
            json.dumps(schema["parameters"]),
            data_model_type=data_model_types.data_model,
            data_model_root_type=data_model_types.root_model,
            data_model_field_type=data_model_types.field_model,
            data_type_manager_type=data_model_types.data_type_manager,
            dump_resolve_reference_action=data_model_types.dump_resolve_reference_action,
            use_schema_description=True,
            validation=False,
            class_name="Model",
            strip_default_none=schema.get("strict", False), # default parameters are not supported in strict mode
            # custom_template_dir=Path('/Users/vrsen/Projects/agency-swarm/agency-swarm/agency_swarm/tools/data_schema_templates')
        )

        result = parser.parse()

        # Prepend necessary imports to the generated code string
        imports_str = "from typing import List, Dict, Any, Optional, Union, Set, Tuple, Literal\nfrom enum import Enum\n"
        result = imports_str + result

        # --- FIX: Remove problematic __future__ import added by generator --- #
        result = result.replace("from __future__ import annotations\n", "")
        # --- END FIX --- #

        # Rebuild the model to ensure it's fully defined
        result += "\n\nModel.model_rebuild(force=True)"

        # Execute the result to extract the model
        exec_globals = {
            # We might not strictly need all these in globals anymore if they are imported in the string,
            # but keeping them shouldn't hurt.
            "List": List,
            "Dict": Dict,
            "Type": Type,
            "Union": Union,
            "Optional": Optional,
            "datetime": datetime,
            "date": date,
            "Set": Set,
            "Tuple": Tuple,
            "Any": Any,
            "Callable": Callable,
            "Decimal": Decimal,
            "Literal": Literal,
            "Enum": Enum,
        }

        exec(result, exec_globals)
        model = exec_globals.get("Model")

        if not model:
            raise ValueError(f"Could not extract model from schema {schema['name']}")

        # --- FIX: Explicitly rebuild the generated model --- #
        try:
            model.model_rebuild(force=True)
        except Exception as e:
            print(f"Warning: Could not rebuild model {schema['name']} after exec: {e}")
        # --- END FIX --- #

        class ToolConfig:
            strict: bool = schema.get("strict", False)

        tool = type(
            schema["name"],
            (BaseTool, model),
            {
                "__doc__": schema.get("description", ""),
                "run": callback,
            },
        )

        tool.ToolConfig = ToolConfig

        return tool

    @staticmethod
    def from_openapi_schema(
        schema: Union[str, dict],
        headers: Dict[str, str] = None,
        params: Dict[str, Any] = None,
        strict: bool = False,
    ) -> List[Type[BaseTool]]:
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
                # Use the callback factory to create a unique callback for each path/method
                # This ensures each callback captures the correct path value
                callback = ToolFactory._create_callback_for_path(
                    path, method, openapi_spec, params, headers
                )

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
                            param_properties[param["name"]]["description"] = param[
                                "description"
                            ]
                        if "required" in param and param["required"]:
                            required_params.append(param["name"])
                        if "example" in param:
                            param_properties[param["name"]]["example"] = param[
                                "example"
                            ]
                        if "examples" in param:
                            param_properties[param["name"]]["examples"] = param[
                                "examples"
                            ]

                    schema["properties"]["parameters"] = {
                        "type": "object",
                        "properties": param_properties,
                        "required": required_params,
                    }

                function = {
                    "name": function_name,
                    "description": desc,
                    "parameters": schema,
                    "strict": strict,
                }

                tools.append(ToolFactory.from_openai_schema(function, callback))

        return tools

    @staticmethod
    def _create_callback_for_path(path, method, openapi_spec, params, headers):
        """
        Creates a callback function for a specific path and method.
        This is a factory function that captures the current values of path and method.

        Parameters:
            path: The path to create the callback for.
            method: The HTTP method to use.
            openapi_spec: The OpenAPI specification.
            params: Additional parameters to include in the request.
            headers: Headers to include in the request.

        Returns:
            An async callback function that makes the appropriate HTTP request.
        """

        async def callback(self):
            url = openapi_spec["servers"][0]["url"] + path
            parameters = self.model_dump().get("parameters", {})
            # replace all parameters in url
            for param, value in parameters.items():
                if "{" + str(param) + "}" in url:
                    url = url.replace(f"{{{param}}}", str(value))
                    parameters[param] = None
            url = url.rstrip("/")
            parameters = {k: v for k, v in parameters.items() if v is not None}
            parameters = {**parameters, **params} if params else parameters
            async with httpx.AsyncClient(
                timeout=90
            ) as client:  # Set custom read timeout to 10 seconds
                if method == "get":
                    response = await client.get(url, params=parameters, headers=headers)
                elif method == "post":
                    response = await client.post(
                        url,
                        params=parameters,
                        json=self.model_dump().get("requestBody", None),
                        headers=headers,
                    )
                elif method == "put":
                    response = await client.put(
                        url,
                        params=parameters,
                        json=self.model_dump().get("requestBody", None),
                        headers=headers,
                    )
                elif method == "delete":
                    response = await client.delete(
                        url,
                        params=parameters,
                        json=self.model_dump().get("requestBody", None),
                        headers=headers,
                    )
                return response.json()

        return callback

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
    def from_mcp(server):
        tool_definitions = server.list_tools()
        tools = []

        if tool_definitions == []:
            raise Exception(f"No tools found in MCP server: {server.name}")

        for definition in tool_definitions:
            # Handle both dictionary and object formats
            if isinstance(definition, dict):
                name = definition.get("name")
                description = definition.get("description", "")
                parameters = definition.get("inputSchema", {})
            else:
                # Access attributes from object
                name = getattr(definition, "name", "")
                description = getattr(definition, "description", "")
                parameters = getattr(definition, "inputSchema", {})
                # The returned object might have the parameters as a property or a method
                if callable(parameters):
                    parameters = parameters()
            # Check if any parameter has a default value
            has_default_values = False
            if isinstance(parameters, dict) and "properties" in parameters:
                for param_props in parameters["properties"].values():
                    if "default" in param_props:
                        has_default_values = True
                        break
            # If any parameter has a default value, set strict to False
            if has_default_values and server.strict:
                logger.warning("Non-supported tool parameter found, disabling strict mode.")
                server.strict = False

            # Create a factory function to properly capture the tool name
            def create_callback(tool_name):
                async def callback(self, **kwargs):

                    # Extract arguments from the model_dump, excluding any internal attributes
                    args = {
                        k: v
                        for k, v in self.model_dump(exclude_unset=True, by_alias=True).items()
                        if not k.startswith("_") and k != "self"
                    }

                    # Call the tool with just the arguments, not the whole model
                    try:
                        result = server.call_tool(tool_name, args)
                        logger.info(f"Tool {tool_name} output: {result}")
                    except Exception as e:
                        logger.error(f"Tool call failed: {type(e).__name__}: {e!r}")
                        return f"Tool call failed: {type(e).__name__}: {e!r}"

                    if hasattr(result, "content") and result.content:
                        # Extract text from the first content item if it exists
                        if len(result.content) > 0 and hasattr(
                            result.content[0], "text"
                        ):
                            return result.content[0].text
                        # Try to convert the content to a string
                        return str(result.content)
                    # Fallback: try to get the result attribute or convert the entire object to string
                    if hasattr(result, "result"):
                        return result.result

                    return str(result)

                return callback

            callback = create_callback(name)

            tool = ToolFactory.from_openai_schema(
                {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                    "strict": server.strict
                },
                callback,
            )
            tools.append(tool)

        return tools

    @staticmethod
    def get_openapi_schema(
        tools: List[Type[BaseTool]],
        url: str,
        title="Agent Tools",
        description="A collection of tools.",
    ) -> str:
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
            "info": {"title": title, "description": description, "version": "v1.0.0"},
            "servers": [
                {
                    "url": url,
                }
            ],
            "paths": {},
            "components": {
                "schemas": {},
                "securitySchemes": {"apiKey": {"type": "apiKey"}},
            },
        }

        for tool in tools:
            if not issubclass(tool, BaseTool):
                continue

            openai_schema = tool.openai_schema
            defs = {}
            if "$defs" in openai_schema["parameters"]:
                defs = openai_schema["parameters"]["$defs"]
                del openai_schema["parameters"]["$defs"]

            schema["paths"]["/" + openai_schema["name"]] = {
                "post": {
                    "description": openai_schema["description"],
                    "operationId": openai_schema["name"],
                    "x-openai-isConsequential": False,
                    "parameters": [],
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": openai_schema["parameters"]}
                        }
                    },
                }
            }

            schema["components"]["schemas"].update(defs)

        schema = json.dumps(schema, indent=2).replace(
            "#/$defs/", "#/components/schemas/"
        )

        return schema
