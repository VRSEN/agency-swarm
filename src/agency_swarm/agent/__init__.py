"""
Agent domain services.

This package contains domain-specific functions extracted from the Agent class
to maintain clean separation of concerns and reduce file sizes.
"""

from .execution import Execution
from .initialization import handle_deprecated_parameters, separate_kwargs, setup_file_manager
from .messages import (
    adjust_history_for_claude,
    ensure_tool_calls_content_safety,
    resolve_token_settings,
    sanitize_tool_calls_in_history,
)
from .subagents import register_subagent
from .tools import add_tool, load_tools_from_folder, parse_schemas, validate_hosted_tools

__all__ = [
    # Tool functions
    "add_tool",
    "load_tools_from_folder",
    "parse_schemas",
    "validate_hosted_tools",
    # Subagent functions
    "register_subagent",
    # Message functions
    "sanitize_tool_calls_in_history",
    "ensure_tool_calls_content_safety",
    "resolve_token_settings",
    "adjust_history_for_claude",
    # Initialization functions
    "handle_deprecated_parameters",
    "separate_kwargs",
    "setup_file_manager",
    # Classes for complex state management
    "Execution",
]
