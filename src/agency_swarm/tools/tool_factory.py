"""Tool factory for converting various tool formats to Agency Swarm tools."""

import asyncio
import importlib.util
import inspect
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Union

from agents import Agent as SDKAgent, FunctionTool
from agents.mcp.server import MCPServer
from agents.run_context import RunContextWrapper
from agents.strict_schema import ensure_strict_json_schema

from .base_tool import BaseTool
from .langchain_converter import from_langchain_tool, from_langchain_tools
from .mcp_converter import from_mcp
from .openapi_converter import from_openai_schema, from_openapi_schema

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent as AgencyAgent

logger = logging.getLogger(__name__)


class ToolFactory:
    """Factory for converting various tool formats to Agency Swarm tools."""

    @staticmethod
    def from_langchain_tools(tools: list) -> list[FunctionTool]:
        """
        Converts a list of langchain tools into a list of FunctionTools.

        Parameters:
            tools: The langchain tools to convert.

        Returns:
            A list of FunctionTools.
        """
        return from_langchain_tools(tools)

    @staticmethod
    def from_langchain_tool(tool) -> FunctionTool:
        """
        Converts a langchain tool into a FunctionTool.

        Parameters:
            tool: The langchain tool to convert.

        Returns:
            A FunctionTool.
        """
        return from_langchain_tool(tool)

    @staticmethod
    def from_mcp(
        mcp_servers: list[MCPServer],
        convert_schemas_to_strict: bool = False,
        context: RunContextWrapper[Any] | None = None,
        agent: Union["AgencyAgent", SDKAgent, None] = None,
        as_base_tool: bool = True,
    ) -> list[type[BaseTool]] | list[FunctionTool]:
        """
        Convert MCP servers into standalone tool instances.

        Args:
            mcp_servers: List of MCP servers to convert
            convert_schemas_to_strict: Whether to convert schemas to strict mode
            context: Run context wrapper
            agent: Agent instance
            as_base_tool: If True, return BaseTool classes; if False, return FunctionTool instances

        Returns:
            List of BaseTool classes or FunctionTool instances depending on as_base_tool parameter
        """
        return from_mcp(mcp_servers, convert_schemas_to_strict, context, agent, as_base_tool)

    @staticmethod
    def from_openai_schema(schema: dict[str, Any], function_name: str) -> tuple[type | None, type | None]:
        """
        Converts an OpenAI schema into Pydantic models for parameters and request body.
        Returns:
            A dict with keys 'parameters' and 'request_body' (if present), each mapping to a Pydantic model.
        """
        return from_openai_schema(schema, function_name)

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
        return from_openapi_schema(schema, headers=headers, params=params, strict=strict, timeout=timeout)

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
        module = None
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
        if module:
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
                    return await tool_instance.run()
                # Always run sync run() in a thread for async compatibility
                return await asyncio.to_thread(tool_instance.run)
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
