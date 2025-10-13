"""Utility functions for working with model configurations."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent

# Reasoning model prefixes that support reasoning parameter but not temperature
REASONING_MODEL_PREFIXES = ("gpt-5", "o3", "o4-mini", "o1")


def is_reasoning_model(model_name: str | None) -> bool:
    """Determine if a model supports reasoning capabilities.

    Reasoning models include o-series models (o1, o3, o4-mini) and GPT-5 series.
    These models support the reasoning parameter but not temperature.

    Parameters
    ----------
    model_name : str | None
        The model identifier (e.g., "gpt-5", "o1-preview", "gpt-4o")

    Returns
    -------
    bool
        True if the model supports reasoning, False otherwise
    """
    if not model_name:
        return False
    return any(model_name.startswith(prefix) for prefix in REASONING_MODEL_PREFIXES)


def get_agent_capabilities(agent: "Agent") -> list[str]:
    """Detect capabilities of an agent based on its configuration.

    Capability detection rules:
    - "tools": Agent defines custom FunctionTool, BaseTool, MCP servers, or HostedMCPTool
    - "reasoning": Model supports reasoning (o-series, gpt-5) or has reasoning parameter
    - "file_search": Agent uses FileSearchTool
    - "code_interpreter": Agent uses CodeInterpreterTool
    - "web_search": Agent uses WebSearchTool

    Parameters
    ----------
    agent : Agent
        The agent to analyze

    Returns
    -------
    list[str]
        List of capability strings in consistent order
    """
    from agents import CodeInterpreterTool, FileSearchTool, FunctionTool, HostedMCPTool, WebSearchTool

    capabilities: list[str] = []

    # Check for custom tools (FunctionTool, BaseTool, MCP servers, HostedMCPTool)
    has_custom_tools = False
    has_file_search = False
    has_code_interpreter = False
    has_web_search = False

    # Check agent.tools
    if agent.tools:
        for tool in agent.tools:
            # Check for hosted tools (not custom)
            if isinstance(tool, FileSearchTool):
                has_file_search = True
            elif isinstance(tool, CodeInterpreterTool):
                has_code_interpreter = True
            elif isinstance(tool, WebSearchTool):
                has_web_search = True
            elif isinstance(tool, HostedMCPTool | FunctionTool):
                # HostedMCPTool and FunctionTool are custom tools
                has_custom_tools = True
            elif hasattr(tool, "__class__") and hasattr(tool.__class__, "__bases__"):
                # Check if it's a BaseTool subclass
                # BaseTool is from agency_swarm.tools.base_tool
                try:
                    from agency_swarm.tools.base_tool import BaseTool

                    if isinstance(tool, type) and issubclass(tool, BaseTool):
                        has_custom_tools = True
                    elif isinstance(tool, BaseTool):
                        has_custom_tools = True
                except ImportError:
                    pass

    # Check for MCP servers
    mcp_servers = getattr(agent, "mcp_servers", None)
    if mcp_servers and isinstance(mcp_servers, list) and len(mcp_servers) > 0:
        has_custom_tools = True

    # Add capabilities in consistent order
    if has_custom_tools:
        capabilities.append("tools")

    # Check for reasoning capability
    model_name = getattr(agent, "model", None)
    if isinstance(model_name, str) and is_reasoning_model(model_name):
        capabilities.append("reasoning")
    else:
        # Also check for reasoning parameter in model_settings
        model_settings = getattr(agent, "model_settings", None)
        if model_settings:
            reasoning = getattr(model_settings, "reasoning", None)
            if reasoning is not None:
                capabilities.append("reasoning")

    if has_code_interpreter:
        capabilities.append("code_interpreter")

    if has_web_search:
        capabilities.append("web_search")

    if has_file_search:
        capabilities.append("file_search")

    return capabilities
