"""
Agent domain services.

This package contains domain-specific functions extracted from the Agent class
to maintain clean separation of concerns and reduce file sizes.
"""

from .execution import Execution
from .initialization import handle_deprecated_parameters, separate_kwargs, setup_file_manager, wrap_input_guardrails
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
    # Initialization functions
    "handle_deprecated_parameters",
    "separate_kwargs",
    "setup_file_manager",
    "wrap_input_guardrails",
    # Classes for complex state management
    "Execution",
]
