"""
Tool management functionality for agents.

This module handles tool registration, validation, loading from folders,
and OpenAPI schema parsing for the Agent class.
"""

import inspect
import logging
import os
import typing
from pathlib import Path
from typing import TYPE_CHECKING, get_args

from agents import FunctionTool, Tool

from agency_swarm.tools import BaseTool, ToolFactory, validate_openapi_spec

logger = logging.getLogger(__name__)


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

    tool_types = get_args(Tool)
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
    Validates that all hosted tools in the tools list are properly initialized instances.

    Hosted tools are OpenAI's built-in tools like FileSearchTool, WebSearchTool, etc.
    These must be instantiated before being passed to the agent.

    Args:
        tools: List of tools to validate

    Raises:
        TypeError: If any hosted tool class is passed uninitialized
    """

    # Get all hosted tool types from the Tool union (excluding FunctionTool)
    hosted_tool_types = typing.get_args(Tool)
    hosted_tool_types = tuple(t for t in hosted_tool_types if t != FunctionTool)

    uninitialized_tools = []

    for i, tool in enumerate(tools):
        # Check if the tool is a class (uninitialized) rather than an instance
        if inspect.isclass(tool) and tool in hosted_tool_types:
            uninitialized_tools.append(f"  - {tool.__name__} at index {i}")

    if uninitialized_tools:
        tool_list = "\n".join(uninitialized_tools)
        hosted_tool_names = [t.__name__ for t in hosted_tool_types]

        raise TypeError(
            f"Hosted tools must be initialized before passing to the agent.\n\n"
            f"Found uninitialized hosted tool classes:\n{tool_list}\n\n"
            f"Hosted tools ({', '.join(hosted_tool_names)}) are OpenAI's built-in tools "
            f"that require proper instantiation with their configuration parameters.\n"
            f"Please initialize these tools according to their schemas before adding them to the agent."
        )
