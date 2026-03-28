"""Utility functions for working with model configurations."""

import logging
from pathlib import Path
from types import UnionType
from typing import TYPE_CHECKING, Any, Protocol, Union, cast, get_args, get_origin

from agents import FunctionTool, Model, Tool
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel

from agency_swarm.agent.file_manager import (
    CODE_INTERPRETER_FILE_EXTENSIONS,
    FILE_SEARCH_FILE_EXTENSIONS,
    IMAGE_FILE_EXTENSIONS,
)

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent

# Reasoning model prefixes that support reasoning parameter but not temperature
REASONING_MODEL_PREFIXES = ("gpt-5", "o3", "o4-mini", "o1")
logger = logging.getLogger(__name__)


def get_model_name(model: str | Model | None) -> str | None:
    """Extract a string model name from supported Agents SDK model types."""
    if isinstance(model, str):
        return model
    if isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        return str(model.model)
    if isinstance(model, Model):
        try:
            return str(cast("_ModelWithName", model).model)
        except AttributeError:
            return None
    return None


def get_usage_tracking_model_name(model: str | Model | None) -> str | None:
    """Extract the model name that should be used for usage pricing.

    Some proxy-backed models expose a stable public alias (for example
    ``openclaw:main``) while real token pricing depends on the upstream provider
    model. Those adapters can attach ``_agency_swarm_usage_model_name`` to the
    model object so cost calculation stays accurate without changing the public
    alias.
    """
    if isinstance(model, Model):
        try:
            usage_model_name = cast("_ModelWithUsageName", model)._agency_swarm_usage_model_name
        except AttributeError:
            usage_model_name = None
        if isinstance(usage_model_name, str) and usage_model_name.strip():
            return usage_model_name.strip()

    return get_model_name(model)


def get_default_settings_model_name(model: str | Model | None) -> str | None:
    """Extract the SDK default-settings lookup key for a model."""
    if isinstance(model, Model):
        try:
            default_settings_model_name = cast("_ModelWithDefaultSettingsName", model)._agency_swarm_default_model_name
        except AttributeError:
            default_settings_model_name = None
        if isinstance(default_settings_model_name, str) and default_settings_model_name.strip():
            return default_settings_model_name.strip()

    return get_model_name(model)


def supports_previous_response_id(model: str | Model | None) -> bool:
    """Return True when the model is expected to resume server-side state from previous_response_id."""
    if isinstance(model, OpenAIResponsesModel):
        return True
    if isinstance(model, OpenAIChatCompletionsModel):
        return False
    if isinstance(model, str):
        if "/" in model:
            prefix, _rest = model.split("/", 1)
            return prefix == "openai"
        return ":" not in model
    return False


def is_reasoning_model(model: str | Model | None) -> bool:
    """Determine if a model supports reasoning capabilities.

    Reasoning models include o-series models (o1, o3, o4-mini) and GPT-5 series.
    These models support the reasoning parameter but not temperature.

    Parameters
    ----------
    model : str | Model | None
        The model identifier (e.g., "gpt-5", "o1-preview", "gpt-4o")

    Returns
    -------
    bool
        True if the model supports reasoning, False otherwise
    """
    if not model:
        return False
    model_name = None
    if isinstance(model, Model):
        # Safely get either 'name' or 'model' attribute
        model_name = getattr(model, "name", None) or getattr(model, "model", None)
        # In case it's a Litellm model, remove the provider name
        if isinstance(model_name, str) and len(split := model_name.split("/")) > 1:
            model_name = split[-1]
    elif isinstance(model, str):
        model_name = model
    else:
        logger.warning(f"Unknown type for model: {model}")
        return False
    if not model_name:
        logger.warning(f"Could not extract model name for model: {model}")
        return False
    return any(model_name.startswith(prefix) for prefix in REASONING_MODEL_PREFIXES)


def get_agent_capabilities(agent: "Agent") -> list[str]:
    """Detect capabilities of an agent based on its configuration.

    Capability detection rules:
    - "tools": Agent defines custom FunctionTool or MCP servers
    - Hosted tools report their name (e.g., "code_interpreter", "web_search", "file_search", "hosted_mcp")
    - "reasoning": Model supports reasoning (o-series, gpt-5) or has reasoning parameter

    Parameters
    ----------
    agent : Agent
        The agent to analyze

    Returns
    -------
    list[str]
        List of capability strings in consistent order
    """
    capabilities: list[str] = []
    detected_tool_capabilities: list[str] = []
    has_custom_tools = False

    for tool in agent.tools:
        if _isinstance_or_subclass(tool, Tool):
            if _isinstance_or_subclass(tool, FunctionTool):
                has_custom_tools = True
            else:
                name = getattr(tool, "name", None)
                if isinstance(name, str) and name and name not in detected_tool_capabilities:
                    detected_tool_capabilities.append(name)
        else:
            has_custom_tools = True

    if agent.mcp_servers:
        has_custom_tools = True

    if has_custom_tools and "tools" not in capabilities:
        capabilities.append("tools")

    model_name = agent.model
    has_reasoning = isinstance(model_name, str) and is_reasoning_model(model_name)
    if not has_reasoning:
        has_reasoning = agent.model_settings.reasoning is not None

    if has_reasoning:
        capabilities.append("reasoning")

    ordered_tool_names = ["code_interpreter", "web_search", "file_search", "hosted_mcp"]
    for tool_name in ordered_tool_names:
        if tool_name in detected_tool_capabilities and tool_name not in capabilities:
            capabilities.append(tool_name)

    for tool_name in detected_tool_capabilities:
        if tool_name not in capabilities:
            capabilities.append(tool_name)

    for tool_name in _detect_files_folder_capabilities(agent):
        if tool_name not in capabilities:
            capabilities.append(tool_name)

    return capabilities


def _detect_files_folder_capabilities(agent: "Agent") -> list[str]:
    path = getattr(agent, "files_folder_path", None)
    if not isinstance(path, Path) or not path.exists() or not path.is_dir():
        return []

    has_code = False
    has_search = False
    for file in path.iterdir():
        if not file.is_file():
            continue
        ext = file.suffix.lower()
        if not has_code and ext in CODE_INTERPRETER_FILE_EXTENSIONS + IMAGE_FILE_EXTENSIONS:
            has_code = True
        if not has_search and ext in FILE_SEARCH_FILE_EXTENSIONS:
            has_search = True
        if has_code and has_search:
            break

    result: list[str] = []
    if has_code:
        result.append("code_interpreter")
    if has_search:
        result.append("file_search")
    return result


class _ModelWithName(Protocol):
    model: str


class _ModelWithUsageName(Protocol):
    _agency_swarm_usage_model_name: str


class _ModelWithDefaultSettingsName(Protocol):
    _agency_swarm_default_model_name: str


def _runtime_types_for_check(cls: Any) -> tuple[type[Any], ...]:
    origin = get_origin(cls)
    if origin in (Union, UnionType):
        runtime_types: list[type[Any]] = []
        for arg in get_args(cls):
            runtime_types.extend(_runtime_types_for_check(arg))
        return tuple(runtime_types)
    if origin is None:
        return (cls,) if isinstance(cls, type) else ()
    if isinstance(origin, type):
        return (origin,)
    return ()


def _isinstance_or_subclass(obj: object, cls: Any) -> bool:
    """Return True when obj is an instance of cls or a subclass reference."""

    runtime_types = _runtime_types_for_check(cls)
    if not runtime_types:
        return False
    return isinstance(obj, runtime_types) or (isinstance(obj, type) and any(issubclass(obj, t) for t in runtime_types))
