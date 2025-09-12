import asyncio
import importlib.util
import inspect
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
import jsonref
from agents import FunctionTool
from agents.exceptions import ModelBehaviorError
from agents.run_context import RunContextWrapper
from agents.strict_schema import ensure_strict_json_schema
from pydantic import BaseModel, ValidationError

from .base_tool import BaseTool
from .utils import generate_model_from_schema

logger = logging.getLogger(__name__)


class ToolFactory:
    @staticmethod
    def from_langchain_tools(tools: list) -> list[FunctionTool]:
        """
        Converts a list of langchain tools into a list of FunctionTools.

        Parameters:
            tools: The langchain tools to convert.

        Returns:
            A list of FunctionTools.
        """
        converted_tools = []
        for tool in tools:
            converted_tools.append(ToolFactory.from_langchain_tool(tool))

        return converted_tools

    @staticmethod
    def from_langchain_tool(tool) -> FunctionTool:
        """
        Converts a langchain tool into a FunctionTool.

        Parameters:
            tool: The langchain tool to convert.

        Returns:
            A FunctionTool.
        """
        try:
            from langchain_community.tools import format_tool_to_openai_function
        except ImportError as e:
            raise ImportError("You must install langchain to use this method.") from e

        if inspect.isclass(tool):
            tool = tool()

        # Get the OpenAI function schema from langchain tool
        openai_schema = format_tool_to_openai_function(tool)

        # Extract tool information
        tool_name = openai_schema.get("name", tool.__class__.__name__)
        tool_description = openai_schema.get("description", tool.description)

        # Get parameters schema - this should be the full JSON schema for the FunctionTool
        parameters_schema = openai_schema.get("parameters", {})

        # Ensure proper schema structure for FunctionTool
        if not parameters_schema:
            parameters_schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}

        # Create the async callback function
        async def on_invoke_tool(ctx, input_json: str):
            """Callback function that executes the langchain tool."""
            try:
                args = json.loads(input_json) if input_json else {}
            except Exception as e:
                return f"Error: Invalid JSON input: {e}"
            try:
                # Call the langchain tool
                result = tool.run(args)
                return str(result)
            except TypeError:
                # Try with single argument if direct dict fails (langchain specifics)
                if len(args) == 1:
                    result = tool.run(list(args.values())[0])
                    return str(result)
                else:
                    return f"Error parsing input for tool '{tool.__class__.__name__}'. Please open an issue on github."
            except Exception as e:
                return f"Error running LangChain tool: {e}"

        # Create and return the FunctionTool
        func_tool = FunctionTool(
            name=tool_name,
            description=tool_description.strip(),
            params_json_schema=parameters_schema,
            on_invoke_tool=on_invoke_tool,
            strict_json_schema=False,  # LangChain tools are not strict by default
        )

        return func_tool

    @staticmethod
    def from_openai_schema(schema: dict[str, Any], function_name: str) -> tuple[type | None, type | None]:
        """
        Converts an OpenAI schema into Pydantic models for parameters and request body.
        Returns:
            A dict with keys 'parameters' and 'request_body' (if present), each mapping to a Pydantic model.
        """
        param_model = None
        request_body_model = None
        strict = schema.get("strict", False)
        camel_func_name = "".join(word.capitalize() for word in function_name.replace("_", " ").split())

        # Parameters model
        if "parameters" in schema["properties"] and schema["properties"]["parameters"]:
            param_model = generate_model_from_schema(schema["properties"]["parameters"], camel_func_name, strict)

        # Request body model (first schema in any content type)
        request_body_schema = schema.get("properties", {}).get("requestBody", {})
        if request_body_schema:
            request_body_model = generate_model_from_schema(request_body_schema, camel_func_name, strict)

        return param_model, request_body_model

    @staticmethod
    def from_openapi_schema(
        schema: str | dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        strict: bool = False,
        timeout: int = 90,
    ) -> list[FunctionTool]:
        """
        Converts an OpenAPI JSON or dictionary describing a single endpoint into one or more FunctionTool instances.

        Args:
            schema (str | dict): Full OpenAPI JSON string or dictionary.
            headers (dict[str, str] | None, optional): Extra HTTP headers to send with each call. Defaults to None.
            params (dict[str, Any] | None, optional): Extra query parameters to append to every call. Defaults to None.
            strict (bool, optional): Applies `strict` standard to schema that the OpenAI API expects. Defaults to True.
            timeout (int, optional): HTTP timeout in seconds. Defaults to 90.

        Returns:
            list[FunctionTool]: List of FunctionTool instances generated from the OpenAPI endpoint.
        """

        if isinstance(schema, dict):
            openapi = jsonref.JsonRef.replace_refs(schema)
        else:
            openapi = jsonref.loads(schema)

        headers = {k: v for k, v in (headers or {}).items() if v is not None}

        tools: list[FunctionTool] = []

        for path, verbs in openapi["paths"].items():
            for verb, verb_spec_ref in verbs.items():
                verb_spec = jsonref.replace_refs(verb_spec_ref)

                # Build OpenAI-compatible JSON schema

                function_name = verb_spec.get("operationId")
                description = verb_spec.get("description") or verb_spec.get("summary", "")

                req_body_schema = None
                if content := verb_spec.get("requestBody", {}).get("content", {}):
                    for content_obj in content.values():
                        if "schema" in content_obj:
                            req_body_schema = content_obj["schema"]
                            break

                param_properties: dict[str, Any] = {}
                required_params: list[str] = []
                for p in verb_spec.get("parameters", []):
                    # normalise spec → openapi3 guarantees p["schema"] when parsing
                    if "schema" not in p and "type" in p:
                        p["schema"] = {"type": p["type"]}
                    param_schema = param_properties.setdefault(p["name"], p["schema"].copy())
                    if "description" in p:
                        param_schema["description"] = p["description"]
                    if "example" in p:
                        param_schema["example"] = p["example"]
                    if "examples" in p:
                        param_schema["examples"] = p["examples"]
                    if p.get("required"):
                        required_params.append(p["name"])

                # nested `"parameters"` object for legacy agents
                parameters_obj_schema: dict[str, Any] = {
                    "type": "object",
                    "properties": param_properties,
                    "required": required_params,
                    "additionalProperties": False if strict else True,
                }

                # full JSON schema for the FunctionTool
                tool_schema: dict[str, Any] = {
                    "type": "object",
                    "properties": {
                        "parameters": parameters_obj_schema,
                    },
                    "required": ["parameters"],
                    "additionalProperties": False if strict else True,
                    "strict": strict,
                }
                if req_body_schema:
                    req_body_schema = req_body_schema.copy()
                    if strict:
                        req_body_schema.setdefault("additionalProperties", False)
                    tool_schema["properties"]["requestBody"] = req_body_schema
                    tool_schema["required"].append("requestBody")

                if strict:
                    tool_schema = ensure_strict_json_schema(tool_schema)

                # Callback factory (captures current verb & path)
                on_invoke_tool = ToolFactory._create_invoke_for_path(
                    path, verb, openapi, tool_schema, function_name, headers, params, timeout
                )

                tool = FunctionTool(
                    name=function_name,
                    description=description,
                    params_json_schema=tool_schema,
                    on_invoke_tool=on_invoke_tool,
                    strict_json_schema=strict,
                )
                tools.append(tool)

        return tools

    @staticmethod
    def _create_invoke_for_path(path, verb, openapi, tool_schema, function_name, headers=None, params=None, timeout=90):
        """
        Creates a callback function for a specific path and method.
        This is a factory function that captures the current values of path and method.

        Parameters:
            path: The path to create the callback for.
            verb: The HTTP method to use.
            openapi: The OpenAPI specification.
            tool_schema: The schema for the tool.
            function_name: The function/operation name.
            headers: Headers to include in the request.
            params: Additional parameters to include in the request.
            timeout: HTTP timeout in seconds.

        Returns:
            An async callback function that makes the appropriate HTTP request.
        """
        param_model, request_body_model = ToolFactory.from_openai_schema(tool_schema, function_name)
        fixed_params = params or {}

        async def _invoke(
            ctx: RunContextWrapper[Any],
            input: str,
            *,
            verb_: str = verb,
            path_: str = path,
            param_model_: type[BaseModel] = param_model,
            request_body_model_: type[BaseModel] = request_body_model,
        ):
            """Actual HTTP call executed by the agent."""
            payload = json.loads(input) if input else {}

            # split out parts for old-style structure
            param_container: dict[str, Any] = payload.get("parameters", {})

            if param_model_:
                # Validate parameters
                try:
                    parsed = param_model_(**param_container) if param_container else param_model_()
                    param_container = parsed.model_dump()
                except ValidationError as e:
                    raise ModelBehaviorError(
                        f"Invalid JSON input in parameters for tool {param_model_.__name__}: {e}"
                    ) from e

            body_payload = payload.get("requestBody")

            if request_body_model_:
                # Validate request body
                try:
                    parsed = request_body_model_(**body_payload) if body_payload else request_body_model_()
                    body_payload = parsed.model_dump()
                except ValidationError as e:
                    raise ModelBehaviorError(
                        f"Invalid JSON input in request body for tool {request_body_model_.__name__}: {e}"
                    ) from e

            url = f"{openapi['servers'][0]['url']}{path_}"
            for key, val in param_container.items():
                token = f"{{{key}}}"
                if token in url:
                    url = url.replace(token, str(val))
                    # null-out so it doesn't go into query string
                    param_container[key] = None
            url = url.rstrip("/")

            query_params = {k: v for k, v in param_container.items() if v is not None}
            if fixed_params:
                query_params = {**query_params, **fixed_params}

            json_body = body_payload if verb_.lower() in {"post", "put", "patch", "delete"} else None

            logger.info(f"Calling URL: {url}\nQuery Params: {query_params}\nJSON Body: {json_body}")

            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.request(
                    verb_.upper(),
                    url,
                    params=query_params,
                    json=json_body,
                    headers=headers,
                )
                try:
                    logger.info(f"Response from {url}: {resp.json()}")
                    return resp.json()
                except Exception:
                    return resp.text

        return _invoke

    @staticmethod
    def from_file(file_path: str | Path) -> list[type[BaseTool] | FunctionTool]:
        """Dynamically imports a BaseTool class from a Python file within a package structure.

        Parameters:
            file_path: The file path to the Python file containing the BaseTool class.

        Returns:
            The imported BaseTool class.
        """
        file = Path(file_path)
        tools: list[type[BaseTool] | FunctionTool] = []

        module_name = file.stem
        try:
            spec = importlib.util.spec_from_file_location(module_name, file)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[f"{module_name}_{uuid.uuid4().hex}"] = module
                spec.loader.exec_module(module)
            else:
                logger.error("Unable to import tool module %s", file)
        except Exception as e:
            logger.error("Error importing tool module %s: %s", file, e)

        # BaseTool: expect class with same name as file
        base_tool = getattr(module, module_name, None)
        if inspect.isclass(base_tool) and issubclass(base_tool, BaseTool) and base_tool is not BaseTool:
            try:
                tools.append(base_tool)
            except Exception as e:
                logger.error("Error adapting tool %s: %s", module_name, e)

        # FunctionTool instances defined in the module
        for obj in module.__dict__.values():
            if isinstance(obj, FunctionTool):
                tools.append(obj)

        return tools

    @staticmethod
    def get_openapi_schema(
        tools: list[type[BaseTool] | FunctionTool],
        url: str,
        title="Agent Tools",
        description="A collection of tools.",
    ) -> str:
        """
        Generates an OpenAPI schema from a list of BaseTools.

        Parameters:
            tools: BaseTools or FunctionTools to generate the schema from.
            url: The base URL for the schema.
            title: The title of the schema.
            description: The description of the schema.

        Returns:
            A JSON string representing the OpenAPI schema with all the tools combined as separate endpoints.
        """
        schema: dict[str, Any] = {
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
            if inspect.isclass(tool) and issubclass(tool, BaseTool):
                openai_schema = tool.openai_schema
                logger.debug(f"OpenAPI schema for {tool.__name__}: {openai_schema}")
            elif isinstance(tool, FunctionTool):
                openai_schema = {}
                openai_schema["parameters"] = tool.params_json_schema
                openai_schema["name"] = tool.name
                logger.debug(f"OpenAPI schema for {tool.name}: {openai_schema}")
            else:
                raise TypeError(f"Tool {tool} is not a BaseTool or FunctionTool.")

            defs = {}
            if "$defs" in openai_schema["parameters"]:
                defs = openai_schema["parameters"]["$defs"]
                del openai_schema["parameters"]["$defs"]

            schema["paths"]["/" + openai_schema["name"]] = {
                "post": {
                    "description": openai_schema["description"] if "description" in openai_schema else "",
                    "operationId": openai_schema["name"],
                    "x-openai-isConsequential": False,
                    "parameters": [],
                    "requestBody": {"content": {"application/json": {"schema": openai_schema["parameters"]}}},
                }
            }

            if isinstance(defs, dict):
                schema["components"]["schemas"].update(defs)

        schema_str = json.dumps(schema, indent=2).replace("#/$defs/", "#/components/schemas/")

        return schema_str

    @staticmethod
    def adapt_base_tool(base_tool: type[BaseTool]) -> FunctionTool:
        """
        Adapts a BaseTool (class-based) to a FunctionTool (function-based).
        Args:
            base_tool: A class inheriting from BaseTool.
        Returns:
            A FunctionTool instance.
        """
        name = base_tool.__name__
        description = base_tool.__doc__ or ""
        if bool(getattr(base_tool, "__abstractmethods__", set())):
            raise TypeError(f"BaseTool '{name}' must implement all abstract methods.")
        if description == "":
            logger.warning(f"Warning: Tool {name} has no docstring.")
        # Use the Pydantic model schema for parameters
        params_json_schema = base_tool.model_json_schema()
        if getattr(base_tool.ToolConfig, "strict", False):
            params_json_schema = ensure_strict_json_schema(params_json_schema)
        # Remove title/description at the top level, keep only in properties
        params_json_schema = {k: v for k, v in params_json_schema.items() if k not in ("title", "description")}
        params_json_schema["additionalProperties"] = False

        # The on_invoke_tool function
        async def on_invoke_tool(ctx, input_json: str):
            # Parse input_json to dict
            import json

            try:
                args = json.loads(input_json) if input_json else {}
            except Exception as e:
                return f"Error: Invalid JSON input: {e}"
            try:
                # Instantiate the BaseTool with args
                tool_instance = base_tool(**args)
                # Pass context to the tool instance if available
                if ctx is not None:
                    tool_instance._context = ctx
                if inspect.iscoroutinefunction(tool_instance.run):
                    result = await tool_instance.run()
                else:
                    # Always run sync run() in a thread for async compatibility
                    result = await asyncio.to_thread(tool_instance.run)
                return str(result)
            except Exception as e:
                return f"Error running BaseTool: {e}"

        func_tool = FunctionTool(
            name=name,
            description=description.strip(),
            params_json_schema=params_json_schema,
            on_invoke_tool=on_invoke_tool,
            strict_json_schema=getattr(base_tool.ToolConfig, "strict", False) or False,
        )
        # Propagate one_call_at_a_time from BaseTool.ToolConfig to the FunctionTool instance
        # Store as a private attribute since FunctionTool doesn't have this field
        if hasattr(base_tool.ToolConfig, "one_call_at_a_time"):
            func_tool.one_call_at_a_time = bool(base_tool.ToolConfig.one_call_at_a_time)  # type: ignore[attr-defined]
        return func_tool
