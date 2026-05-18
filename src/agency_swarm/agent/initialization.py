"""
Agent initialization functionality.

This module handles the complex initialization process for agents,
including setting up file management.
"""

import asyncio
import copy
import dataclasses
import inspect
import logging
import re
import threading
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from typing import TYPE_CHECKING, Any, NamedTuple

from agents import (
    Agent as BaseAgent,
    FunctionTool,
    GuardrailFunctionOutput,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
)
from agents.models.default_models import get_default_model_settings as get_sdk_default_model_settings

from agency_swarm.agent.attachment_manager import AttachmentManager
from agency_swarm.agent.constants import FRAMEWORK_DEFAULT_MODEL
from agency_swarm.agent.file_manager import AgentFileManager
from agency_swarm.agent.runner_compat_graph import collect_runner_compatible_agents
from agency_swarm.messages.response_input_sanitizer import ensure_store_false_reasoning_encrypted_content
from agency_swarm.tools import BaseTool, ToolFactory
from agency_swarm.tools.function_tool_compat import normalize_function_tool
from agency_swarm.utils.model_utils import REASONING_MODEL_PREFIXES, get_default_settings_model_name

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent

logger = logging.getLogger(__name__)

_INPUT_GUARDRAIL_WRAPPED_ATTR = "_agency_swarm_input_guardrail_wrapped"
_GPT_5_MINIMAL_REASONING_FALLBACKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^gpt-5(?:\.\d+)?(?:-mini|-nano|-codex)?(?:-\d{4}-\d{2}-\d{2})?$"), "low"),
    (re.compile(r"^gpt-5(?:\.\d+)?-pro(?:-\d{4}-\d{2}-\d{2})?$"), "medium"),
)
_MODEL_FAMILY_DEFAULT_FIELDS: tuple[str, ...] = ("reasoning", "verbosity")
# Agency Swarm defaults applied when the SDK leaves a field unset
# include_usage=True enables streaming usage tracking for LiteLLM models
_FRAMEWORK_DEFAULT_MODEL_SETTINGS = ModelSettings(truncation="auto", include_usage=True)
_RUNNER_COMPAT_LOCK_ATTR = "_agency_swarm_runner_model_settings_lock"
_RUNNER_COMPAT_LOCK_CREATION_LOCK = threading.Lock()
_RUNNER_COMPAT_OWNER: ContextVar[object | None] = ContextVar("agency_swarm_runner_compat_owner", default=None)


def _get_runner_compat_task_owner() -> object:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return task if task is not None else threading.current_thread()


def _get_framework_default_model_settings(model: str | None = None) -> ModelSettings:
    """Get SDK defaults for a model and layer Agency Swarm defaults on top."""
    base = get_sdk_default_model_settings(model)
    updates = {
        field.name: getattr(_FRAMEWORK_DEFAULT_MODEL_SETTINGS, field.name)
        for field in dataclasses.fields(ModelSettings)
        if getattr(base, field.name) is None and getattr(_FRAMEWORK_DEFAULT_MODEL_SETTINGS, field.name) is not None
    }
    return dataclasses.replace(base, **updates) if updates else base


def _replace_reasoning_effort(reasoning: Any, effort: str) -> Any:
    if hasattr(reasoning, "model_copy"):
        return reasoning.model_copy(update={"effort": effort})
    cloned = copy.copy(reasoning)
    cloned.effort = effort
    return cloned


def normalize_incompatible_model_settings(
    model_name: str | None,
    settings: ModelSettings,
    *,
    omit_unsupported_temperature: bool = False,
) -> ModelSettings:
    """Downgrade user-specified settings that current model families reject."""
    normalized = settings
    canonical_model_name = model_name.split("/")[-1].lower() if model_name else None

    if (
        omit_unsupported_temperature
        and normalized.temperature is not None
        and canonical_model_name
        and canonical_model_name.startswith(REASONING_MODEL_PREFIXES)
    ):
        warnings.warn(
            f"{canonical_model_name or model_name} does not support temperature; omitting the explicit value.",
            UserWarning,
            stacklevel=3,
        )
        normalized = dataclasses.replace(normalized, temperature=None)

    reasoning = normalized.reasoning
    if reasoning is None or getattr(reasoning, "effort", None) != "minimal" or not canonical_model_name:
        return normalized

    for pattern, fallback_effort in _GPT_5_MINIMAL_REASONING_FALLBACKS:
        if pattern.fullmatch(canonical_model_name):
            warnings.warn(
                f"{canonical_model_name} does not support reasoning.effort='minimal'; "
                f"using '{fallback_effort}' instead.",
                UserWarning,
                stacklevel=3,
            )
            return dataclasses.replace(normalized, reasoning=_replace_reasoning_effort(reasoning, fallback_effort))

    return normalized


def normalize_runner_model_settings(model: Any, settings: ModelSettings) -> ModelSettings:
    """Return model settings safe to send to the current SDK model."""
    model_name = get_default_settings_model_name(model)
    return normalize_incompatible_model_settings(model_name, settings, omit_unsupported_temperature=True)


def _needs_family_default_refresh(source_model: Any, target_model: Any) -> bool:
    return get_default_settings_model_name(source_model) != get_default_settings_model_name(target_model)


def _refresh_run_override_model_family_defaults(
    source_model: Any,
    target_model: Any,
    settings: ModelSettings,
) -> ModelSettings:
    """Recompute target model-family defaults while preserving caller-tuned fields."""
    source_defaults = _get_framework_default_model_settings(get_default_settings_model_name(source_model))
    cleared = copy.deepcopy(settings)
    for field_name in _MODEL_FAMILY_DEFAULT_FIELDS:
        if getattr(cleared, field_name) == getattr(source_defaults, field_name):
            setattr(cleared, field_name, None)
    kwargs: dict[str, Any] = {"model": target_model, "model_settings": cleared}
    apply_framework_defaults(kwargs)
    return kwargs["model_settings"]


class RunnerCompatibleRun(NamedTuple):
    agent: Any
    run_config: RunConfig


class _RunnerCompatReentrantLock:
    def __init__(self) -> None:
        self._gate = threading.Lock()
        self._same_owner_gate = threading.Lock()
        self._state_lock = threading.Lock()
        self._owner: object | None = None
        self._owner_task: object | None = None
        # Child tasks inherit the ContextVar owner, so sibling re-entries need their own gate.
        self._same_owner_task: object | None = None
        self._same_owner_depth = 0
        self._depth = 0

    async def acquire(self, *, settings_mutation: bool) -> bool:
        owner = _RUNNER_COMPAT_OWNER.get()
        if owner is None:
            raise RuntimeError("runner compatibility lock requires an active owner")
        task_owner = _get_runner_compat_task_owner()
        while True:
            with self._state_lock:
                if self._owner is owner:
                    if not settings_mutation:
                        return False
                    if self._owner_task is task_owner:
                        self._depth += 1
                        return True
                    if self._same_owner_task is task_owner:
                        self._same_owner_depth += 1
                        self._depth += 1
                        return True
                    acquire_same_owner_gate = True
                else:
                    acquire_same_owner_gate = False

            if acquire_same_owner_gate:
                if self._same_owner_gate.acquire(blocking=False):
                    with self._state_lock:
                        if self._owner is owner and self._same_owner_task is None:
                            self._same_owner_task = task_owner
                            self._same_owner_depth = 1
                            self._depth += 1
                            return True
                    self._same_owner_gate.release()
            if self._gate.acquire(blocking=False):
                with self._state_lock:
                    if self._owner is None:
                        self._owner, self._owner_task, self._depth = owner, task_owner, 1
                        return True
                self._gate.release()
            await asyncio.sleep(0.001)

    def release(self) -> None:
        task_owner = _get_runner_compat_task_owner()
        release_same_owner_gate = False
        release_gate = False
        with self._state_lock:
            if self._owner is not _RUNNER_COMPAT_OWNER.get():
                raise RuntimeError("runner compatibility lock released by non-owner")
            if self._owner_task is task_owner:
                self._depth -= 1
            elif self._same_owner_task is task_owner:
                self._same_owner_depth -= 1
                self._depth -= 1
                if self._same_owner_depth == 0:
                    self._same_owner_task = None
                    release_same_owner_gate = True
            else:
                raise RuntimeError("runner compatibility lock released by non-owner task")

            if self._depth == 0:
                self._owner = None
                self._owner_task = None
                release_gate = True
        if release_same_owner_gate:
            self._same_owner_gate.release()
        if release_gate:
            self._gate.release()


def _get_agent_model_settings_lock(agent: Any) -> _RunnerCompatReentrantLock:
    lock = getattr(agent, _RUNNER_COMPAT_LOCK_ATTR, None)
    if not isinstance(lock, _RunnerCompatReentrantLock):
        with _RUNNER_COMPAT_LOCK_CREATION_LOCK:
            lock = getattr(agent, _RUNNER_COMPAT_LOCK_ATTR, None)
            if not isinstance(lock, _RunnerCompatReentrantLock):
                lock = _RunnerCompatReentrantLock()
                setattr(agent, _RUNNER_COMPAT_LOCK_ATTR, lock)
    return lock


def _normalize_runner_run_model_settings(
    agent: Any,
    run_config: RunConfig,
    protected_agents: tuple[Any, ...],
) -> ModelSettings | None:
    original_run_settings = run_config.model_settings
    if not isinstance(original_run_settings, ModelSettings):
        return original_run_settings

    if run_config.model is not None:
        model_targets: tuple[Any, ...] = (run_config.model,)
    else:
        model_targets = tuple(getattr(protected_agent, "model", None) for protected_agent in protected_agents)
        if not model_targets:
            model_targets = (getattr(agent, "model", None),)

    normalized_settings = original_run_settings
    for model_target in model_targets:
        normalized_settings = normalize_runner_model_settings(model_target, normalized_settings)
    return normalized_settings


@asynccontextmanager
async def use_runner_compatible_model_settings(
    agent: Any,
    run_config: RunConfig,
    master_context: Any | None = None,
) -> AsyncIterator[RunnerCompatibleRun]:
    """Temporarily normalize public Agent settings while protected by per-agent locks."""
    lock_agents, settings_agents = collect_runner_compatible_agents(agent, master_context)
    protected_agents = tuple(sorted(lock_agents, key=id))
    runner_settings_agents = tuple(sorted(settings_agents, key=id))
    runner_settings_agent_ids = {id(protected_agent) for protected_agent in runner_settings_agents}
    acquired_locks: list[_RunnerCompatReentrantLock] = []
    original_agent_settings: list[tuple[Any, ModelSettings]] = []
    runner_run_settings = _normalize_runner_run_model_settings(agent, run_config, runner_settings_agents)
    owner_token = _RUNNER_COMPAT_OWNER.set(object()) if _RUNNER_COMPAT_OWNER.get() is None else None

    try:
        for protected_agent in protected_agents:
            lock = _get_agent_model_settings_lock(protected_agent)
            acquired = await lock.acquire(settings_mutation=id(protected_agent) in runner_settings_agent_ids)
            if acquired:
                acquired_locks.append(lock)

        for protected_agent in runner_settings_agents:
            original_settings = getattr(protected_agent, "model_settings", None)
            if not isinstance(original_settings, ModelSettings):
                continue
            source_model = getattr(protected_agent, "model", None)
            agent_model = run_config.model or source_model
            compatible_settings = original_settings
            if run_config.model is not None and _needs_family_default_refresh(source_model, run_config.model):
                compatible_settings = _refresh_run_override_model_family_defaults(
                    source_model,
                    run_config.model,
                    original_settings,
                )
            protected_agent.model_settings = normalize_runner_model_settings(agent_model, compatible_settings)
            original_agent_settings.append((protected_agent, original_settings))

        yield RunnerCompatibleRun(agent, dataclasses.replace(run_config, model_settings=runner_run_settings))
    finally:
        for protected_agent, original_settings in reversed(original_agent_settings):
            protected_agent.model_settings = original_settings
        for lock in reversed(acquired_locks):
            lock.release()
        if owner_token is not None:
            _RUNNER_COMPAT_OWNER.reset(owner_token)


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
    "return_input_guardrail_errors": ("Removed; use `raise_input_guardrail_error` with inverse value semantics."),
    "response_format": "Use `output_type` on the Agent (a Python type).",
    "tool_resources": "Use `files_folder` and Agent file APIs.",
    "file_search": "Use `files_folder` to manage vector store + file search.",
    "file_ids": "Use `files_folder` to associate files with vector stores.",
    "send_message_tool_class": "Configure per-flow tools via `Agency(communication_flows=...)`.",
    "examples": "Include examples directly in `instructions`, or manage them in your own prompt building.",
}


def normalize_input_guardrail_error_kwargs(kwargs: dict[str, Any]) -> None:
    """Normalize input guardrail exception-control kwargs in-place."""
    canonical = "raise_input_guardrail_error"
    deprecated_alias = "throw_input_guardrail_error"

    if deprecated_alias not in kwargs:
        return

    deprecated_alias_value = bool(kwargs[deprecated_alias])
    if canonical in kwargs:
        canonical_value = bool(kwargs[canonical])
        if canonical_value != deprecated_alias_value:
            raise TypeError(
                "Conflicting values for `raise_input_guardrail_error` and "
                "`throw_input_guardrail_error`. Provide only one or use matching values."
            )
    else:
        kwargs[canonical] = deprecated_alias_value

    warnings.warn(
        "`throw_input_guardrail_error` is deprecated and will be removed in a future release. "
        "Use `raise_input_guardrail_error` instead.",
        DeprecationWarning,
        stacklevel=3,
    )
    kwargs.pop(deprecated_alias, None)


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
        elif isinstance(tool, FunctionTool):
            tools_list[i] = normalize_function_tool(tool)


def apply_framework_defaults(kwargs: dict[str, Any]) -> None:
    """
    Apply Agency Swarm framework defaults to model settings.

    Layers Agency Swarm defaults (e.g., truncation="auto") on top of the agents
    SDK defaults, preserving model-specific SDK settings (like GPT-5 reasoning).

    Args:
        kwargs: The initialization keyword arguments (modified in place)
    """
    model_arg = kwargs.get("model")
    model_name = FRAMEWORK_DEFAULT_MODEL if model_arg is None else get_default_settings_model_name(model_arg)
    base_defaults = _get_framework_default_model_settings(model_name)

    existing_settings = kwargs.get("model_settings")
    if existing_settings is None:
        kwargs["model_settings"] = base_defaults
        ensure_store_false_reasoning_encrypted_content(kwargs["model_settings"])
        return

    if isinstance(existing_settings, dict):
        existing_settings = ModelSettings(**{k: v for k, v in existing_settings.items() if v is not None})

    if not isinstance(existing_settings, ModelSettings):
        raise TypeError("model_settings must be a ModelSettings instance or dict")

    resolved_settings = base_defaults.resolve(existing_settings)
    kwargs["model_settings"] = normalize_incompatible_model_settings(model_name, resolved_settings)
    ensure_store_false_reasoning_encrypted_content(kwargs["model_settings"])


def refresh_model_family_defaults(model: Any, settings: ModelSettings | None) -> ModelSettings:
    """Recompute model-family defaults for a model swap without wiping caller tuning."""
    cleared = copy.deepcopy(settings) if settings is not None else ModelSettings()
    for field_name in _MODEL_FAMILY_DEFAULT_FIELDS:
        setattr(cleared, field_name, None)
    kwargs: dict[str, Any] = {"model": model, "model_settings": cleared}
    apply_framework_defaults(kwargs)
    return kwargs["model_settings"]


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

    if base_agent_params.get("model") is None:
        base_agent_params["model"] = FRAMEWORK_DEFAULT_MODEL

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
