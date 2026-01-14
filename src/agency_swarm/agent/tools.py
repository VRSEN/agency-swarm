"""
Tool management functionality for agents.

This module handles tool registration, validation, loading from folders,
and OpenAPI schema parsing for the Agent class.
"""

import inspect
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, get_args, get_origin

from agents import FunctionTool, Tool

from agency_swarm.tools import BaseTool, ToolFactory, validate_openapi_spec

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent


def add_tool(agent: "Agent", tool: Tool) -> None:
    """
    Adds a `Tool` instance to the agent's list of tools.

    Ensures the tool is a valid `agents.Tool` instance and prevents adding
    tools with duplicate names.

    Args:
        agent: The agent to add the tool to
        tool: The `agents.Tool` instance to add

    Raises:
        TypeError: If the provided `tool` is not an instance of `agents.Tool`
    """
    if any(getattr(t, "name", None) == getattr(tool, "name", None) for t in agent.tools):
        logger.warning(
            f"Tool with name '{getattr(tool, 'name', '(unknown)')}' already exists for agent '{agent.name}'. Skipping."
        )
        return

    tool_types = _runtime_tool_types()
    if not isinstance(tool, tool_types):
        raise TypeError(f"Expected an instance of Tool, got {type(tool)}")

    # Ensure FunctionTools get one-call guard if needed
    _attach_one_call_guard(tool, agent)

    agent.tools.append(tool)
    logger.debug(f"Tool '{getattr(tool, 'name', '(unknown)')}' added to agent '{agent.name}'")


def load_tools_from_folder(agent: "Agent") -> None:
    """Load tools defined in ``tools_folder`` and add them to the agent.

    Supports both ``BaseTool`` subclasses and ``FunctionTool``
    instances created via the ``@function_tool`` decorator.

    Args:
        agent: The agent to load tools for
    """
    if not agent.tools_folder:
        return

    folder_path = Path(agent.tools_folder)
    if not folder_path.is_absolute():
        folder_path = Path(agent.get_class_folder_path()) / folder_path

    if not folder_path.is_dir():
        logger.warning("Tools folder path is not a directory. Skipping... %s", folder_path)
        return

    for file in folder_path.iterdir():
        if not file.is_file() or file.suffix != ".py" or file.name.startswith("_"):
            continue

        tools = ToolFactory.from_file(file)
        for tool in tools:
            if inspect.isclass(tool) and issubclass(tool, BaseTool):
                try:
                    adapted_tool = ToolFactory.adapt_base_tool(tool)
                    add_tool(agent, adapted_tool)
                except Exception as e:
                    logger.error("Error adapting tool %s: %s", file, e)
                    continue
            elif isinstance(tool, FunctionTool):
                # tool is already a FunctionTool instance
                add_tool(agent, tool)
            else:
                logger.warning(f"Skipping unknown tool type: {type(tool)}")


def parse_schemas(agent: "Agent") -> None:
    """Parse OpenAPI schemas from a schemas folder and create tools.

    Args:
        agent: The agent to parse schemas for
    """
    schemas_folder = agent.schemas_folder
    if not schemas_folder:
        return

    # Accept str or Path; normalize to string
    f_path = str(schemas_folder)

    if not os.path.isdir(f_path):
        f_path = os.path.join(agent.get_class_folder_path(), f_path)
        f_path = os.path.normpath(f_path)

    if os.path.isdir(f_path):
        entries = os.listdir(f_path)
        entries = [e for e in entries if not e.startswith(".")]
        schema_paths = [os.path.join(f_path, e) for e in entries]

        for schema_file_path in schema_paths:
            with open(schema_file_path) as f:
                openapi_spec = f.read()
            try:
                validate_openapi_spec(openapi_spec)
            except Exception as e:
                logger.error("Invalid OpenAPI schema: " + os.path.basename(schema_file_path))
                raise e
            try:
                headers = None
                params = None
                base = os.path.basename(schema_file_path)
                if base in agent.api_headers:
                    headers = agent.api_headers[base]
                if base in agent.api_params:
                    params = agent.api_params[base]
                tools = ToolFactory.from_openapi_schema(openapi_spec, headers=headers, params=params)
            except Exception:
                logger.error(
                    "Error parsing OpenAPI schema: " + os.path.basename(schema_file_path),
                    exc_info=True,
                )
                raise

            for tool in tools:
                add_tool(agent, tool)
    else:
        logger.warning(
            f"Schemas folder path is not a directory. Skipping... {f_path}. "
            f"Make sure to create a 'schemas' folder inside the agent folder, or "
            f"set a valid path in the schemas_folder argument."
        )


def validate_hosted_tools(tools: list) -> None:
    """
    Validates that hosted tools in the tools list are properly initialized instances.

    Hosted tools are OpenAI's built-in tools like FileSearchTool, WebSearchTool, etc.
    These must be instantiated before being passed to the agent.

    This function is intentionally *hosted-tools-only*. It does not validate non-hosted
    tool entries; use validate_tools() for full validation of an Agent's `tools` list.

    Args:
        tools: List of tools to validate

    Raises:
        TypeError: If any hosted tool class is passed uninitialized
    """
    tool_types = _runtime_tool_types()
    # Get all hosted tool types from the Tool union (excluding FunctionTool)
    hosted_tool_types = tuple(t for t in tool_types if t != FunctionTool)

    for tool in tools:
        # Check if the tool is a class (uninitialized) rather than an instance.
        tool_class = tool if inspect.isclass(tool) else get_origin(tool)
        if tool_class in hosted_tool_types:
            tool_name = tool_class.__name__ if inspect.isclass(tool_class) else str(tool)
            raise TypeError(
                f"Tool '{tool_name}' is a hosted tool class. Create an instance first, like {tool_name}(...),"
                " then pass that to the agent."
            )


def validate_tools(tools: list) -> None:
    """
    Validates the `tools` list passed to an Agent.

    Responsibilities:
    - Reject uninitialized hosted tool classes (delegates to validate_hosted_tools()).
    - Reject FunctionTool classes (must be instances, created via @function_tool/ToolFactory).
    - Reject BaseTool *instances* (must be passed as classes and adapted by initialization.py).
    - Reject any non-Tool entries early with a clear error.
    """
    validate_hosted_tools(tools)

    tool_types = _runtime_tool_types()

    for tool in tools:
        # BaseTool classes are valid inputs for Agent(tools=[...]); they are adapted
        # to FunctionTool instances by initialization.handle_deprecated_parameters().
        if inspect.isclass(tool) and issubclass(tool, BaseTool):
            continue

        if inspect.isclass(tool) and issubclass(tool, FunctionTool):
            tool_name = tool.__name__
            raise TypeError(
                f"Tool '{tool_name}' is a FunctionTool class. Use @function_tool or ToolFactory to create a tool."
            )

        if isinstance(tool, BaseTool):
            tool_name = type(tool).__name__
            raise TypeError(
                f"Tool '{tool_name}' is a BaseTool instance. Pass the BaseTool class (like {tool_name}),"
                f" not {tool_name}()."
            )

        # At this point, BaseTool classes should already have been adapted upstream
        # (see agency_swarm.agent.initialization.handle_deprecated_parameters()).
        if not isinstance(tool, tool_types):
            tool_name = tool.__name__ if inspect.isclass(tool) else type(tool).__name__
            raise TypeError(
                f"Tool '{tool_name}' is not a supported tool. Use @function_tool, a BaseTool class, or a hosted"
                " tool instance."
            )


def _attach_one_call_guard(tool: Tool, agent: "Agent") -> None:
    """Attach a one-call-at-a-time guard to a FunctionTool in-place (idempotent)."""
    if not isinstance(tool, FunctionTool):
        return

    original_on_invoke = getattr(tool, "on_invoke_tool", None)
    if not callable(original_on_invoke) or getattr(tool, "_one_call_guard_installed", False):
        return

    one_call = bool(getattr(tool, "one_call_at_a_time", False))
    if one_call:
        tool.description = (
            f"{tool.description} This tool can only be used sequentially. "
            "Do not try to run it in parallel with other tools."
        )

    async def guarded_on_invoke(ctx, input_json: str):
        concurrency_manager = None
        master_context = getattr(ctx, "context", None)
        runtime_state = None
        if master_context is not None and getattr(master_context, "agent_runtime_state", None):
            runtime_state = master_context.agent_runtime_state.get(agent.name)
        if runtime_state is not None:
            concurrency_manager = runtime_state.tool_concurrency_manager
        else:
            concurrency_manager = agent.tool_concurrency_manager

        # First, block if any one_call tool is currently running for this agent
        busy, owner = concurrency_manager.is_lock_active()
        if busy:
            return (
                f"Error: Tool concurrency violation. '{owner or 'unknown'}' tool is still running. "
                f"No other tools may run until it finishes. Wait for the tool to finish before running another one."
            )

        # If this tool enforces one_call and ANY tool is already running for this agent, block
        if one_call and concurrency_manager.get_active_count() > 0:
            return (
                f"Error: Tool concurrency violation. Tool {tool.name} can only be used sequentially. "
                "Make sure no other tools are running while using this tool."
            )

        # Track that a tool is starting for this agent
        concurrency_manager.increment_active_count()

        # If this tool enforces one_call, acquire the lock for the duration of this run
        if one_call:
            concurrency_manager.acquire_lock(getattr(tool, "name", "FunctionTool"))

        try:
            return await original_on_invoke(ctx, input_json)
        finally:
            # Release lock if held
            if one_call:
                concurrency_manager.release_lock()
            # Decrement active tool count
            concurrency_manager.decrement_active_count()

    tool.on_invoke_tool = guarded_on_invoke  # type: ignore[attr-defined]
    tool._one_call_guard_installed = True  # type: ignore[attr-defined]


def _runtime_tool_types() -> tuple[type, ...]:
    runtime_types: list[type] = []
    for tool_type in get_args(Tool):
        origin = get_origin(tool_type)
        if isinstance(tool_type, type):
            runtime_type = tool_type
        elif isinstance(origin, type):
            runtime_type = origin
        else:
            continue
        if runtime_type not in runtime_types:
            runtime_types.append(runtime_type)
    return tuple(runtime_types)
