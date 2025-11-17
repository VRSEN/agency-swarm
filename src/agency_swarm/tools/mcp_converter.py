"""MCP server to tool conversion utilities."""

import asyncio
import json
import logging
import threading
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Union

from agents import Agent as SDKAgent, FunctionTool, set_tracing_disabled
from agents.mcp.server import MCPServer
from agents.mcp.util import MCPUtil
from agents.run_context import RunContextWrapper
from pydantic import BaseModel, Field, PrivateAttr, create_model

from agency_swarm.tools.mcp_manager import LoopAffineAsyncProxy, default_mcp_manager

from .base_tool import BaseTool

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent as AgencyAgent

logger = logging.getLogger(__name__)


def _create_mcp_base_tool(function_tool: FunctionTool, server_name: str) -> type[BaseTool]:
    """
    Dynamically creates a BaseTool class from a FunctionTool instance.

    Args:
        function_tool: The FunctionTool to wrap
        server_name: Name of the MCP server for debugging

    Returns:
        A BaseTool class that wraps the FunctionTool
    """
    # Create a unique class name first (needed for nested models)
    # Convert snake_case to PascalCase for BaseTool naming convention
    tool_name_parts = function_tool.name.split("_")
    class_name = "".join(word.capitalize() for word in tool_name_parts)

    # Extract schema information
    schema = function_tool.params_json_schema
    properties = schema.get("properties", {})
    required = schema.get("required", [])
    defs = schema.get("$defs", {})

    # Type mapping for JSON schema types to Python types
    type_mapping = {
        "string": str,
        "number": float,
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    # Helper function to resolve $ref
    def resolve_ref(field_schema: dict[str, Any]) -> dict[str, Any]:
        if "$ref" in field_schema:
            ref_path = field_schema["$ref"]
            if ref_path.startswith("#/$defs/"):
                def_name = ref_path.split("/")[-1]
                return defs.get(def_name, field_schema)
        return field_schema

    # Helper function to extract type from schema, handling anyOf/oneOf
    def get_field_type(field_schema: dict[str, Any]) -> Any:
        """Extract Python type from JSON schema, handling unions."""
        json_type = field_schema.get("type")

        # Handle anyOf/oneOf (common for optional fields with null)
        if "anyOf" in field_schema:
            # Try to find the non-null type
            for option in field_schema["anyOf"]:
                if option.get("type") and option["type"] != "null":
                    json_type = option["type"]
                    break
        elif "oneOf" in field_schema:
            # Take the first type
            if field_schema["oneOf"]:
                json_type = field_schema["oneOf"][0].get("type")

        return type_mapping.get(json_type or "string", Any)

    # Recursive function to build nested models
    def build_field_type(field_schema: dict[str, Any], field_name: str, parent_name: str) -> Any:
        """Recursively build field types, creating nested models as needed."""
        # Resolve $ref first
        field_schema = resolve_ref(field_schema)

        json_type = field_schema.get("type")

        # Handle object types with properties (nested models)
        if json_type == "object":
            nested_props = field_schema.get("properties", {})
            nested_required = field_schema.get("required", [])

            if nested_props:
                nested_fields: dict[str, Any] = {}
                for nested_name, nested_schema in nested_props.items():
                    # Recursively build nested field types
                    nested_type = build_field_type(nested_schema, nested_name, f"{parent_name}_{field_name}")
                    nested_desc = nested_schema.get("description", "")

                    if nested_name in nested_required:
                        nested_fields[nested_name] = (nested_type, Field(..., description=nested_desc))
                    else:
                        nested_default = nested_schema.get("default")
                        nested_fields[nested_name] = (nested_type, Field(nested_default, description=nested_desc))

                # Create nested model
                nested_model_name = f"{parent_name}_{field_name}"
                return create_model(nested_model_name, **nested_fields)
            else:
                return dict

        # Return mapped type for primitives (handles anyOf/oneOf)
        return get_field_type(field_schema)

    # First, create models for all definitions in $defs using the recursive builder
    def_models: dict[str, type[BaseModel]] = {}
    if defs:
        for def_name, def_schema in defs.items():
            def_props = def_schema.get("properties", {})
            def_required = def_schema.get("required", [])

            if def_props:
                nested_fields: dict[str, Any] = {}
                for prop_name, prop_info in def_props.items():
                    # Use the recursive builder for proper type resolution
                    prop_type = build_field_type(prop_info, prop_name, def_name)
                    prop_desc = prop_info.get("description", "")
                    is_required = prop_name in def_required

                    if is_required:
                        nested_fields[prop_name] = (prop_type, Field(..., description=prop_desc))
                    else:
                        default_val = prop_info.get("default")
                        nested_fields[prop_name] = (prop_type, Field(default_val, description=prop_desc))

                if nested_fields:
                    def_models[def_name] = create_model(def_name, **nested_fields)

    # Build field definitions for the main Pydantic model
    field_definitions: dict[str, Any] = {}
    for field_name, field_schema in properties.items():
        # Check if this field references a $def
        if "$ref" in field_schema:
            ref_path = field_schema["$ref"]
            if ref_path.startswith("#/$defs/"):
                def_name = ref_path.split("/")[-1]
                if def_name in def_models:
                    field_type = def_models[def_name]
                    field_description = field_schema.get("description", "")

                    if field_name in required:
                        field_definitions[field_name] = (field_type, Field(..., description=field_description))
                    else:
                        field_definitions[field_name] = (field_type, Field(None, description=field_description))
                    continue

        # Build field type recursively
        field_type = build_field_type(field_schema, field_name, class_name)
        field_description = field_schema.get("description", "")

        # Check if field is required
        if field_name in required:
            field_definitions[field_name] = (field_type, Field(..., description=field_description))
        else:
            default_value = field_schema.get("default")
            field_definitions[field_name] = (field_type, Field(default_value, description=field_description))

    # Create the base model with fields
    DynamicModel = create_model(class_name, **field_definitions)

    # Create the BaseTool subclass (inherits metaclass from BaseTool)
    class MCPBaseTool(BaseTool, DynamicModel):  # type: ignore[misc,valid-type]
        """Dynamically created BaseTool wrapper for MCP tool."""

        # Use PrivateAttr with factory to avoid deepcopy issues
        _mcp_function_tool: FunctionTool = PrivateAttr(default_factory=lambda: function_tool)
        _mcp_server_name: str = PrivateAttr(default_factory=lambda: server_name)

        async def run(self) -> str:
            """Execute the MCP tool via the wrapped FunctionTool with automatic reconnection."""
            # Convert instance fields to JSON for the FunctionTool
            args_dict = self.model_dump(exclude={"_mcp_function_tool", "_mcp_server_name"})
            input_json = json.dumps(args_dict)

            # Get context
            ctx = self._context or RunContextWrapper(context=None)

            # Invoke the FunctionTool with retry logic for connection errors
            max_retries = 2
            last_exception = None

            for attempt in range(max_retries):
                try:
                    result = await self._mcp_function_tool.on_invoke_tool(ctx, input_json)  # type: ignore[arg-type]
                    return str(result)
                except Exception as e:
                    last_exception = e

                    # Get error message from multiple sources
                    error_msg = str(e).lower()
                    error_type = type(e).__name__.lower()
                    error_repr = repr(e).lower()

                    # Combine all error information for checking
                    full_error_info = f"{error_msg} {error_type} {error_repr}"

                    # Check if it's a connection-related error
                    # Empty or vague error messages often indicate connection issues
                    has_vague_error = (
                        not error_msg.strip()  # Completely empty
                        or error_msg.endswith(": ")  # Ends with ": " (no actual error detail)
                        or error_msg.endswith(":")  # Ends with ":" (no actual error detail)
                        or len(error_msg.strip()) < 10  # Very short error message
                    )

                    has_connection_keyword = any(
                        keyword in full_error_info
                        for keyword in [
                            "connection",
                            "closed",
                            "disconnected",
                            "timeout",
                            "broken pipe",
                            "session",
                            "not connected",
                            "eof",
                            "reset",
                            "agentsexception",  # SDK exception type
                        ]
                    )

                    is_connection_error = has_vague_error or has_connection_keyword

                    if is_connection_error and attempt < max_retries - 1:
                        logger.warning(
                            f"Connection error on attempt {attempt + 1} for MCP tool {function_tool.name} "
                            f"from {server_name}: {e!r}. Attempting to reconnect..."
                        )

                        # Attempt to reconnect by clearing the driver and re-establishing connection
                        try:
                            await self._attempt_reconnect()
                        except Exception as reconnect_error:
                            logger.error(f"Reconnection attempt failed for {server_name}: {reconnect_error}")

                        # Retry the tool invocation
                        continue

                    # Not a connection error or final attempt
                    logger.error(
                        f"Error invoking MCP tool {function_tool.name} from {server_name} "
                        f"(attempt {attempt + 1}/{max_retries}): {e!r}"
                    )
                    break

            # If we get here, all retries failed
            if last_exception:
                error_details = str(last_exception) if str(last_exception).strip() else repr(last_exception)
                return f"Error: {error_details}"
            return "Error: Unknown error occurred"

        async def _attempt_reconnect(self) -> None:
            """Attempt to reconnect to the MCP server by delegating to the manager."""
            # Get the server from the manager by name
            server = default_mcp_manager.get(self._mcp_server_name)
            if server is None:
                logger.warning(f"Server {self._mcp_server_name} not found in manager")
                return

            # Delegate to the manager's reconnect method
            await default_mcp_manager.reconnect(server)

    # Set the docstring from the FunctionTool
    MCPBaseTool.__doc__ = function_tool.description or f"MCP tool: {function_tool.name}"
    MCPBaseTool.__name__ = class_name

    # Create a unique ToolConfig subclass to avoid mutating the shared BaseTool.ToolConfig
    if function_tool.strict_json_schema:

        class ToolConfig(BaseTool.ToolConfig):
            strict: bool = True

        MCPBaseTool.ToolConfig = ToolConfig  # type: ignore[misc]

    return MCPBaseTool


def _run_coroutine_from_factory(factory: Callable[[], Awaitable[Any]]) -> Any:
    """Execute an async coroutine factory from synchronous code."""
    result: dict[str, Any] = {}
    error: list[BaseException] = []

    def _runner() -> None:
        try:
            coro = factory()
            result["value"] = asyncio.run(coro)  # type: ignore[arg-type]
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)

    thread = threading.Thread(target=_runner, name="tool-factory-mcp-call", daemon=True)
    thread.start()
    thread.join()

    if error:
        raise error[0]
    if "value" not in result:
        raise RuntimeError("Coroutine execution did not produce a result")
    return result["value"]


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
    if not mcp_servers:
        return []

    servers = list(mcp_servers)
    run_context = context or RunContextWrapper(context=None)
    agent_for_fetch: SDKAgent
    if isinstance(agent, SDKAgent):
        agent_for_fetch = agent
    else:
        agent_for_fetch = SDKAgent(name="mcp_tool_loader")

    # Register servers
    server_names = []
    for i, srv in enumerate(list(servers)):
        name = getattr(srv, "name", None)
        if isinstance(name, str) and name != "" and name not in server_names:
            server_names.append(name)
            persistent = default_mcp_manager.get(name) or default_mcp_manager.register(srv)
            if persistent is not servers[i]:
                servers[i] = persistent
        elif name in server_names:
            raise ValueError(
                f"Server {srv} has duplicate name: {name}. "
                "Please provide server with unique names by explicitly specifying the name attribute."
            )
        else:
            raise ValueError(f"Server {srv} has no name provided")

    # Wrap servers in LoopAffineAsyncProxy and ensure drivers are created
    for idx, srv in enumerate(list(servers)):
        if not isinstance(srv, LoopAffineAsyncProxy):
            proxy = LoopAffineAsyncProxy(srv, default_mcp_manager)
            servers[idx] = proxy  # type: ignore[assignment,call-overload]
            srv = proxy  # type: ignore[assignment]

        # Ensure driver is created and connected on the background loop (synchronous)
        default_mcp_manager._ensure_driver(getattr(srv, "_server", srv))

    converted_tools: list[type[BaseTool]] | list[FunctionTool] = []

    # Save the current tracing state before disabling it
    # The SDK doesn't expose a public getter, so we access the internal provider state
    # This is necessary to avoid permanently re-enabling tracing if it was already disabled
    from agents.tracing import get_trace_provider

    trace_provider = get_trace_provider()
    original_tracing_disabled = getattr(trace_provider, "_disabled", False)

    # Temporarily disable tracing to avoid sdk logging a non-existent error
    set_tracing_disabled(True)
    try:
        for server in servers:

            async def _fetch_tools(current_server: MCPServer = server) -> list[FunctionTool]:
                tools = await MCPUtil.get_function_tools(
                    current_server,
                    convert_schemas_to_strict,
                    run_context,
                    agent_for_fetch,
                )
                return [t for t in tools if isinstance(t, FunctionTool)]

            function_tools: list[FunctionTool] = _run_coroutine_from_factory(_fetch_tools)

            if as_base_tool:
                # Convert each FunctionTool to a BaseTool class
                server_name = getattr(server, "name", "unknown")
                for func_tool in function_tools:
                    base_tool_class = _create_mcp_base_tool(func_tool, server_name)
                    converted_tools.append(base_tool_class)  # type: ignore[arg-type]
            else:
                # Return FunctionTool instances directly
                converted_tools.extend(function_tools)  # type: ignore[arg-type]
    finally:
        # Restore the original tracing state instead of unconditionally enabling it
        set_tracing_disabled(original_tracing_disabled)

    return converted_tools
