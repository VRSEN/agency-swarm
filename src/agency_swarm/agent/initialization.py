"""
Agent initialization functionality.

This module handles the complex initialization process for agents,
including handling deprecated parameters and setting up file management.
"""

import inspect
import json
import logging
import warnings
from typing import TYPE_CHECKING, Any

from agents import Agent as BaseAgent, ModelSettings

from agency_swarm.agent.file_manager import AgentFileManager, AttachmentManager
from agency_swarm.tools import BaseTool, ToolFactory

if TYPE_CHECKING:
    from agency_swarm.agent_core import Agent

logger = logging.getLogger(__name__)


def handle_deprecated_parameters(kwargs: dict[str, Any]) -> dict[str, Any]:
    """
    Handle deprecated parameters from older versions of Agency Swarm.

    Processes deprecated parameters, issues warnings, and transforms them
    into the appropriate modern parameters where possible.

    Args:
        kwargs: The initialization keyword arguments

    Returns:
        Dictionary of deprecated arguments that were processed
    """
    deprecated_args_used = {}
    deprecated_model_settings = {}

    # Group deprecated model-related parameters
    model_related_params = [
        "temperature",
        "top_p",
        "max_completion_tokens",
        "max_prompt_tokens",
        "reasoning_effort",
        "truncation_strategy",
    ]

    for param in model_related_params:
        if param in kwargs:
            param_value = kwargs.pop(param)
            warnings.warn(
                f"'{param}' is deprecated as a direct Agent parameter. Configure model settings "
                "via 'model_settings' parameter using a ModelSettings object from the agents SDK.",
                DeprecationWarning,
                stacklevel=3,
            )
            deprecated_args_used[param] = param_value
            deprecated_model_settings[param] = param_value

    if "validation_attempts" in kwargs:
        val_attempts = kwargs.pop("validation_attempts")
        warnings.warn(
            "'validation_attempts' is deprecated.",
            DeprecationWarning,
            stacklevel=3,
        )
        deprecated_args_used["validation_attempts"] = val_attempts

    if "id" in kwargs:
        warnings.warn(
            "'id' parameter (OpenAI Assistant ID) is deprecated and no longer used for loading. "
            "Agent state is managed via PersistenceHooks.",
            DeprecationWarning,
            stacklevel=3,
        )
        deprecated_args_used["id"] = kwargs.pop("id")

    if "response_validator" in kwargs:
        warnings.warn(
            "'response_validator' parameter is deprecated. Use 'output_guardrails' and 'input_guardrails' instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        deprecated_args_used["response_validator"] = kwargs.pop("response_validator")

    if "tool_resources" in kwargs:
        warnings.warn(
            "'tool_resources' is deprecated. File resources should be managed via 'files_folder' "
            "and the 'upload_file' method for Vector Stores.",
            DeprecationWarning,
            stacklevel=3,
        )
        deprecated_args_used["tool_resources"] = kwargs.pop("tool_resources")

    if "file_ids" in kwargs:
        warnings.warn(
            "'file_ids' is deprecated. Use 'files_folder' to associate with Vector Stores "
            "or manage files via Agent methods.",
            DeprecationWarning,
            stacklevel=3,
        )
        deprecated_args_used["file_ids"] = kwargs.pop("file_ids")

    if "examples" in kwargs:
        examples = kwargs.pop("examples")
        warnings.warn(
            "'examples' parameter is deprecated. Consider incorporating examples directly "
            "into the agent's 'instructions'.",
            DeprecationWarning,
            stacklevel=3,
        )
        # Attempt to prepend examples to instructions
        if examples and isinstance(examples, list):
            try:
                # Basic formatting, might need refinement
                examples_str = "\n\nExamples:\n" + "\n".join(f"- {json.dumps(ex)}" for ex in examples)
                current_instructions = kwargs.get("instructions", "")
                kwargs["instructions"] = current_instructions + examples_str
                logger.info("Prepended 'examples' content to agent instructions.")
            except Exception as e:
                logger.warning(f"Could not automatically prepend 'examples' to instructions: {e}")
        deprecated_args_used["examples"] = examples

    if "file_search" in kwargs:
        warnings.warn(
            "'file_search' parameter is deprecated. FileSearchTool is added automatically "
            "if 'files_folder' indicates a Vector Store.",
            DeprecationWarning,
            stacklevel=3,
        )
        deprecated_args_used["file_search"] = kwargs.pop("file_search")

    if "refresh_from_id" in kwargs:
        warnings.warn(
            "'refresh_from_id' is deprecated as loading by Assistant ID is no longer supported.",
            DeprecationWarning,
            stacklevel=3,
        )
        deprecated_args_used["refresh_from_id"] = kwargs.pop("refresh_from_id")

    # Handle response_format parameter mapping to output_type
    if "response_format" in kwargs:
        response_format = kwargs.pop("response_format")
        if "output_type" not in kwargs or kwargs["output_type"] is None:
            kwargs["output_type"] = response_format
        warnings.warn(
            "'response_format' parameter is deprecated. Use 'output_type' instead.",
            DeprecationWarning,
            stacklevel=3,
        )
        deprecated_args_used["response_format"] = response_format

    # Handle deprecated tools
    if "tools" in kwargs:
        tools_list = kwargs["tools"]
        for i, tool in enumerate(tools_list):
            if isinstance(tool, type) and issubclass(tool, BaseTool):
                tools_list[i] = ToolFactory.adapt_base_tool(tool)

    # Merge deprecated model settings into existing model_settings
    if deprecated_model_settings:
        existing_model_settings = kwargs.get("model_settings")

        # Handle existing model_settings being a ModelSettings instance or dict
        if isinstance(existing_model_settings, ModelSettings):
            # Convert ModelSettings to dict for merging
            existing_dict = existing_model_settings.to_json_dict()
        elif existing_model_settings is None:
            existing_dict = {}
        else:
            # Assume it's already a dict
            existing_dict = dict(existing_model_settings)

        # Create a new dict to avoid modifying the original
        merged_model_settings = dict(existing_dict)
        merged_model_settings.update(deprecated_model_settings)

        # to_json_dict returns None for keys that were not set
        keys_to_remove = [key for key, value in merged_model_settings.items() if value is None]
        for key in keys_to_remove:
            merged_model_settings.pop(key)

        resolve_token_settings(merged_model_settings, kwargs.get("name", "unknown"))

        # Create new ModelSettings instance from merged dict
        kwargs["model_settings"] = ModelSettings(**merged_model_settings)

        logger.info(f"Merged deprecated model settings into model_settings: {list(deprecated_model_settings.keys())}")

    # Log if any deprecated args were used
    if deprecated_args_used:
        logger.warning(f"Deprecated Agent parameters used: {list(deprecated_args_used.keys())}")

    return deprecated_args_used


def separate_kwargs(kwargs: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Separate kwargs into base agent parameters and agency swarm specific parameters.

    Args:
        kwargs: All initialization keyword arguments

    Returns:
        Tuple of (base_agent_params, current_agent_params)
    """
    base_agent_params = {}
    current_agent_params = {}

    # Get BaseAgent signature
    try:
        base_sig = inspect.signature(BaseAgent)
        base_param_names = set(base_sig.parameters.keys())
    except ValueError:
        # Fallback if signature inspection fails
        base_param_names = {
            "name",
            "instructions",
            "handoff_description",
            "handoffs",
            "model",
            "model_settings",
            "tools",
            "mcp_servers",
            "mcp_config",
            "input_guardrails",
            "output_guardrails",
            "output_type",
            "hooks",
            "tool_use_behavior",
            "reset_tool_choice",
        }

    # Separate parameters
    for k, v in kwargs.items():
        if k in base_param_names:
            base_agent_params[k] = v
        else:
            current_agent_params[k] = v

    # Add name to current_agent_params as well since we need it
    if "name" in base_agent_params:
        current_agent_params["name"] = base_agent_params["name"]

    # Handoffs should be defined by providing SendMessageHandoff
    if "handoffs" in kwargs:
        logger.warning(
            "Manually setting the 'handoffs' parameter can lead to unexpected behavior. "
            "Handoffs are automatically managed by the Agency based on communication flows. "
            "Use SendMessageHandoff to customize inter-agent communication instead."
        )

    return base_agent_params, current_agent_params


def setup_file_manager(agent: "Agent") -> None:
    """
    Set up the file manager and attachment manager for the agent.

    Args:
        agent: The agent instance
        files_folder: Optional files folder path
    """
    agent.file_manager = AgentFileManager(agent)
    agent.attachment_manager = AttachmentManager(agent)

def resolve_token_settings(model_settings_dict: dict[str, Any], agent_name: str = "unknown") -> None:
    """
    Resolves conflicts between max_tokens, max_prompt_tokens, and max_completion_tokens.

    Args:
        model_settings_dict: Dictionary of model settings to modify in place
        agent_name: Name of the agent for logging purposes
    """
    has_max_tokens = "max_tokens" in model_settings_dict
    has_max_prompt_tokens = "max_prompt_tokens" in model_settings_dict
    has_max_completion_tokens = "max_completion_tokens" in model_settings_dict

    # Since oai only kept 1 parameter to manage tokens, write one of the existing parameters to max_tokens
    if has_max_tokens:
        # If max_tokens is specified, drop prompt and completion tokens
        if has_max_prompt_tokens or has_max_completion_tokens:
            logger.info(
                f"max_tokens is specified, ignoring max_prompt_tokens and max_completion_tokens "
                f"for agent '{agent_name}'"
            )
            model_settings_dict.pop("max_prompt_tokens", None)
            model_settings_dict.pop("max_completion_tokens", None)
    else:
        # If max_tokens is not specified, handle prompt/completion tokens
        if has_max_prompt_tokens and has_max_completion_tokens:
            # Both are present, prefer completion tokens and warn
            model_settings_dict["max_tokens"] = model_settings_dict["max_completion_tokens"]
            model_settings_dict.pop("max_prompt_tokens", None)
            model_settings_dict.pop("max_completion_tokens", None)
            logger.warning(
                f"Both max_prompt_tokens and max_completion_tokens specified for agent '{agent_name}'. "
                f"Using max_completion_tokens value ({model_settings_dict['max_tokens']}) "
                f"for max_tokens and ignoring max_prompt_tokens."
            )
        elif has_max_completion_tokens:
            # Only completion tokens present
            model_settings_dict["max_tokens"] = model_settings_dict["max_completion_tokens"]
            model_settings_dict.pop("max_completion_tokens", None)
        elif has_max_prompt_tokens:
            # Only prompt tokens present
            model_settings_dict["max_tokens"] = model_settings_dict["max_prompt_tokens"]
            model_settings_dict.pop("max_prompt_tokens", None)

    return model_settings_dict
