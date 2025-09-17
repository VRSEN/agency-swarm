"""
Agent initialization functionality.

This module handles the complex initialization process for agents,
including handling deprecated parameters and setting up file management.
"""

import dataclasses
import inspect
import logging
import warnings
from typing import TYPE_CHECKING, Any

from agents import Agent as BaseAgent, GuardrailFunctionOutput, ModelSettings, RunContextWrapper
from agents.models import get_default_model
from openai.types.shared import Reasoning

from agency_swarm.agent.attachment_manager import AttachmentManager
from agency_swarm.agent.file_manager import AgentFileManager
from agency_swarm.tools import BaseTool, ToolFactory

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent

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
        "parallel_tool_calls",
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

            # Map deprecated fields to ModelSettings-compatible keys
            if param == "reasoning_effort":
                # v0.x accepted Literal["low", "medium", "high"]. Map into Reasoning(effort=...).
                try:
                    deprecated_model_settings["reasoning"] = Reasoning(effort=param_value)
                except Exception:
                    warnings.warn(
                        f"Invalid 'reasoning_effort' value: {param_value!r}. Skipping mapping to 'reasoning'.",
                        DeprecationWarning,
                        stacklevel=3,
                    )
            elif param == "truncation_strategy":
                # v1.x uses 'truncation' ("auto" | "disabled"). Pass through value as-is.
                deprecated_model_settings["truncation"] = param_value
            else:
                deprecated_model_settings[param] = param_value

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

    if "return_input_guardrail_errors" in kwargs:
        val = kwargs.pop("return_input_guardrail_errors")
        warnings.warn(
            "'return_input_guardrail_errors' has been renamed to 'throw_input_guardrail_error'.",
            DeprecationWarning,
            stacklevel=3,
        )
        # Inverse semantics: return_input_guardrail_errors=True means do NOT throw
        kwargs["throw_input_guardrail_error"] = not bool(val)
        deprecated_args_used["return_input_guardrail_errors"] = val

    # Handle response_format parameter mapping to output_type
    if "response_format" in kwargs:
        response_format = kwargs.pop("response_format")
        # Only set output_type if it's a proper Python type (e.g., dataclass, pydantic model class)
        if ("output_type" not in kwargs or kwargs["output_type"] is None) and isinstance(response_format, type):
            kwargs["output_type"] = response_format
        else:
            warnings.warn(
                "'response_format' is deprecated and not compatible with v1.x. "
                "Provide a Python type via 'output_type' instead.",
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

        # Filter to only valid ModelSettings fields to avoid TypeErrors from unknown keys
        valid_fields = {f.name for f in dataclasses.fields(ModelSettings)}
        unknown_keys = [k for k in list(merged_model_settings.keys()) if k not in valid_fields]
        for k in unknown_keys:
            merged_model_settings.pop(k, None)
        if unknown_keys:
            agent_name = kwargs.get("name", "unknown")
            logger.warning(f"Ignoring deprecated/unknown model settings for agent '{agent_name}': {unknown_keys}")

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
            "prompt",
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

    if "handoff_description" in base_agent_params and "description" in current_agent_params:
        logger.warning(
            "'description' and 'handoff_description' are both provided. "
            "Using 'description' instead of 'handoff_description'."
        )
        base_agent_params.pop("handoff_description")

    if "model" not in base_agent_params:
        base_agent_params["model"] = get_default_model()

    return base_agent_params, current_agent_params


def setup_file_manager(agent: "Agent") -> None:
    """
    Set up the file manager and attachment manager for the agent.

    Args:
        agent: The agent instance
    """
    agent.file_manager = AgentFileManager(agent)
    agent.attachment_manager = AttachmentManager(agent)


def resolve_token_settings(model_settings_dict: dict[str, Any], agent_name: str = "unknown") -> dict[str, Any]:
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


def wrap_input_guardrails(agent: "Agent"):
    """
    Wraps the input guardrails functions to check if the last message is a user message.
    If yes, extract the user message(s) and pass it to the user's guardrail function
    in a form of a single string or a list of strings.

    Args:
        agent: The agent instance
    """
    for guardrail in agent.input_guardrails:
        if guardrail.guardrail_function.__name__ == "guardrail_wrapper":
            continue

        def create_guardrail_wrapper(guardrail_func):
            def guardrail_wrapper(context: RunContextWrapper, agent: "Agent", chat_history: str | list[dict]):
                if isinstance(chat_history, str):
                    return guardrail_func(context, agent, chat_history)

                user_messages = []
                # Extract concurrent user messages
                for message in reversed(chat_history):
                    if message["role"] == "user":
                        user_messages.append(message["content"])
                    else:
                        break
                if not user_messages:
                    return GuardrailFunctionOutput(
                        output_info="No user input found, skipping guardrail check",
                        tripwire_triggered=False,
                    )
                # If there's only a single user message that is not a list, extract the content
                if len(user_messages) == 1 and isinstance(user_messages[0], str):
                    return guardrail_func(context, agent, user_messages[0])
                else:
                    # Content can be a list, extract text messages out of it and flatten the list
                    user_messages = [
                        item if isinstance(item, str) else item["text"]
                        for subitem in reversed(user_messages)
                        for item in (subitem if isinstance(subitem, list) else [subitem])
                        if isinstance(item, str)
                        or (isinstance(item, dict) and item.get("type") == "input_text" and "text" in item)
                    ]
                    # It might be that user only sends a file/image input without text messages
                    if not user_messages:
                        return GuardrailFunctionOutput(
                            output_info="No user input found, skipping guardrail check",
                            tripwire_triggered=False,
                        )
                    # During filtering, only a single text message might be extracted
                    if len(user_messages) == 1 and isinstance(user_messages[0], str):
                        return guardrail_func(context, agent, user_messages[0])
                    else:
                        return guardrail_func(context, agent, user_messages)

            return guardrail_wrapper

        original_function = guardrail.guardrail_function
        guardrail.guardrail_function = create_guardrail_wrapper(original_function)
