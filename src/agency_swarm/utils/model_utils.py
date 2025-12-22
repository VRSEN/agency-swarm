"""Utility functions for working with model configurations."""

import logging
from typing import TYPE_CHECKING, Any, Protocol, cast

from agents import FunctionTool, Model, Tool
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from agents.models.openai_responses import OpenAIResponsesModel

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

    return capabilities


class _ModelWithName(Protocol):
    model: str


def _isinstance_or_subclass(obj: object, cls: Any) -> bool:
    """Return True when obj is an instance of cls or a subclass reference."""

    return isinstance(obj, cls) or (isinstance(obj, type) and issubclass(obj, cls))
