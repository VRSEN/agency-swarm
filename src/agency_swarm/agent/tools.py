"""
Tool management functionality for agents.

This module handles tool registration, validation, loading from folders,
and OpenAPI schema parsing for the Agent class.
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

from agents import Tool
from openai._utils._logs import logger

from agency_swarm.tools import BaseTool, ToolFactory

if TYPE_CHECKING:
    from agency_swarm.agent_core import Agent


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

    if not isinstance(tool, Tool):
        raise TypeError(f"Expected an instance of Tool, got {type(tool)}")

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
            if issubclass(tool, BaseTool):
                try:
                    tool = ToolFactory.adapt_base_tool(tool)
                except Exception as e:
                    logger.error("Error adapting tool %s: %s", file, e)
                    continue
            add_tool(agent, tool)


def parse_schemas(agent: "Agent") -> None:
    """Parse OpenAPI schemas from the schemas folder and create tools.

    Args:
        agent: The agent to parse schemas for
    """
    schemas_folders = agent.schemas_folder if isinstance(agent.schemas_folder, list) else [agent.schemas_folder]

    for schemas_folder in schemas_folders:
        if isinstance(schemas_folder, str):
            f_path = schemas_folder

            if not os.path.isdir(f_path):
                f_path = os.path.join(agent.get_class_folder_path(), schemas_folder)
                f_path = os.path.normpath(f_path)

            if os.path.isdir(f_path):
                f_paths = os.listdir(f_path)

                f_paths = [f for f in f_paths if not f.startswith(".")]

                f_paths = [os.path.join(f_path, f) for f in f_paths]

                for f_path in f_paths:
                    with open(f_path) as f:
                        openapi_spec = f.read()
                        f.close()  # fix permission error on windows
                    try:
                        ToolFactory.validate_openapi_spec(openapi_spec)
                    except Exception as e:
                        logger.error("Invalid OpenAPI schema: " + os.path.basename(f_path))
                        raise e
                    try:
                        headers = None
                        params = None
                        if os.path.basename(f_path) in agent.api_headers:
                            headers = agent.api_headers[os.path.basename(f_path)]
                        if os.path.basename(f_path) in agent.api_params:
                            params = agent.api_params[os.path.basename(f_path)]
                        tools = ToolFactory.from_openapi_schema(openapi_spec, headers=headers, params=params)
                    except Exception as e:
                        logger.error(
                            "Error parsing OpenAPI schema: " + os.path.basename(f_path),
                            exc_info=True,
                        )
                        raise e

                    for tool in tools:
                        add_tool(agent, tool)

            else:
                logger.warning(
                    f"Schemas folder path is not a directory. Skipping... {f_path}. "
                    f"Make sure to create a 'schemas' folder inside the agent folder, or "
                    f"add it in schemas_folder argument."
                )
        else:
            logger.warning(f"Schemas folders must be strings. Skipping '{schemas_folder}' for agent '{agent.name}'.")
