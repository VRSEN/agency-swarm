"""
Agent initialization functionality.

This module handles the complex initialization process for agents,
including setting up file management.
"""

import dataclasses
import inspect
import logging
from functools import wraps
from typing import TYPE_CHECKING, Any

from agents import Agent as BaseAgent, GuardrailFunctionOutput, ModelSettings, RunContextWrapper
from agents.models import get_default_model
from agents.models.default_models import get_default_model_settings as get_sdk_default_model_settings

from agency_swarm.agent.attachment_manager import AttachmentManager
from agency_swarm.agent.file_manager import AgentFileManager
from agency_swarm.tools import BaseTool, ToolFactory

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent

logger = logging.getLogger(__name__)

_INPUT_GUARDRAIL_WRAPPED_ATTR = "_agency_swarm_input_guardrail_wrapped"

# Agency Swarm defaults applied when the SDK leaves a field unset
# include_usage=True enables streaming usage tracking for LiteLLM models
_FRAMEWORK_DEFAULT_MODEL_SETTINGS = ModelSettings(truncation="auto", include_usage=True)


def _get_framework_default_model_settings(model: str | None = None) -> ModelSettings:
    """Get SDK defaults for a model and layer Agency Swarm defaults on top."""
    base = get_sdk_default_model_settings(model)
    updates = {
        field.name: getattr(_FRAMEWORK_DEFAULT_MODEL_SETTINGS, field.name)
        for field in dataclasses.fields(ModelSettings)
        if getattr(base, field.name) is None and getattr(_FRAMEWORK_DEFAULT_MODEL_SETTINGS, field.name) is not None
    }
    return dataclasses.replace(base, **updates) if updates else base


_DEPRECATED_AGENT_KWARGS: dict[str, str] = {
    # Agent constructor kwargs removed from Agency Swarm (require explicit SDK objects/settings instead).
    "temperature": "Pass `model_settings=ModelSettings(temperature=...)`.",
    "top_p": "Pass `model_settings=ModelSettings(top_p=...)`.",
    "max_completion_tokens": "Pass `model_settings=ModelSettings(max_tokens=...)`.",
    "max_prompt_tokens": "Pass `model_settings=ModelSettings(max_tokens=...)`.",
    "reasoning_effort": "Pass `model_settings=ModelSettings(reasoning=Reasoning(effort=...))`.",
    "truncation_strategy": "Pass `model_settings=ModelSettings(truncation=...)`.",
    "parallel_tool_calls": "Pass `model_settings=ModelSettings(parallel_tool_calls=...)`.",
    "id": "Assistant-ID loading is not supported. Use persistence hooks.",
    "refresh_from_id": "Assistant-ID loading is not supported. Use persistence hooks.",
    "response_validator": "Use `output_guardrails` and `input_guardrails`.",
    "return_input_guardrail_errors": "Use `throw_input_guardrail_error`.",
    "response_format": "Use `output_type` on the Agent (a Python type).",
    "tool_resources": "Use `files_folder` and Agent file APIs.",
    "file_search": "Use `files_folder` to manage vector store + file search.",
    "file_ids": "Use `files_folder` to associate files with vector stores.",
    "send_message_tool_class": "Configure per-flow tools via `Agency(communication_flows=...)`.",
    "examples": "Include examples directly in `instructions`, or manage them in your own prompt building.",
}


def validate_no_deprecated_agent_kwargs(kwargs: dict[str, Any]) -> None:
    """Fail fast if deprecated Agent kwargs are provided."""
    used = [k for k in _DEPRECATED_AGENT_KWARGS.keys() if k in kwargs]
    if not used:
        return

    lines = ["Deprecated Agent parameters are not supported:"]
    for key in used:
        lines.append(f"- {key}: {_DEPRECATED_AGENT_KWARGS[key]}")
    raise TypeError("\n".join(lines))


def normalize_agent_tool_definitions(kwargs: dict[str, Any]) -> None:
    """Normalize tool definitions in-place (e.g., adapt BaseTool subclasses)."""
    if "tools" not in kwargs:
        return
    tools_list = kwargs["tools"]
    if not isinstance(tools_list, list):
        return
    for i, tool in enumerate(tools_list):
        if isinstance(tool, type) and issubclass(tool, BaseTool):
            tools_list[i] = ToolFactory.adapt_base_tool(tool)


def apply_framework_defaults(kwargs: dict[str, Any]) -> None:
    """
    Apply Agency Swarm framework defaults to model settings.

    Layers Agency Swarm defaults (e.g., truncation="auto") on top of the agents
    SDK defaults, preserving model-specific SDK settings (like GPT-5 reasoning).

    Args:
        kwargs: The initialization keyword arguments (modified in place)
    """
    model_arg = kwargs.get("model")
    model_name = model_arg if isinstance(model_arg, str) else None
    base_defaults = _get_framework_default_model_settings(model_name)

    existing_settings = kwargs.get("model_settings")
    if existing_settings is None:
        kwargs["model_settings"] = base_defaults
        return

    if isinstance(existing_settings, dict):
        existing_settings = ModelSettings(**{k: v for k, v in existing_settings.items() if v is not None})

    if not isinstance(existing_settings, ModelSettings):
        raise TypeError("model_settings must be a ModelSettings instance or dict")

    # User-specified values override defaults; unset fields inherit framework+SDK defaults
    kwargs["model_settings"] = base_defaults.resolve(existing_settings)


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

    # Handoffs should be defined via communication flows using the Handoff tool class.
    if "handoffs" in kwargs:
        logger.warning(
            "Manually setting the 'handoffs' parameter on the Agent can lead to unexpected behavior. "
            "Handoffs are automatically managed by the Agency based on communication flows. "
            "To enable handoffs, define them in 'communication_flows' and set the flow's tool class to Handoff."
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


def wrap_input_guardrails(agent: "Agent") -> None:
    """
    Wraps the input guardrails functions to check if the last message is a user message.
    If yes, extract the user message(s) and pass it to the user's guardrail function
    in a form of a single string or a list of strings.

    Args:
        agent: The agent instance
    """
    guardrails = getattr(agent, "input_guardrails", None) or []

    for guardrail in guardrails:
        guardrail_func = getattr(guardrail, "guardrail_function", None)
        if guardrail_func is None or getattr(guardrail_func, _INPUT_GUARDRAIL_WRAPPED_ATTR, False):
            continue

        def create_guardrail_wrapper(guardrail_func):
            @wraps(guardrail_func)
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

            setattr(guardrail_wrapper, _INPUT_GUARDRAIL_WRAPPED_ATTR, True)
            return guardrail_wrapper

        original_function = guardrail.guardrail_function
        guardrail.guardrail_function = create_guardrail_wrapper(original_function)
