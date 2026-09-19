"""Per-request model_settings extra_args normalization."""

import logging
from typing import Any, Literal, cast

from agents import Model, ModelSettings, OpenAIChatCompletionsModel, OpenAIResponsesModel

# LiteLLM is optional - only available if the `litellm` extra is installed
try:
    from agents.extensions.models.litellm_model import LitellmModel

    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False
    LitellmModel = None  # type: ignore[misc, assignment]
from openai.types.shared.reasoning import Reasoning

from agency_swarm import Agent
from agency_swarm.integrations.fastapi_utils.litellm_client_config import (
    _agent_uses_litellm,
    _is_openai_model_name,
    _normalize_litellm_model_name,
)
from agency_swarm.integrations.fastapi_utils.request_models import ClientConfig

# Keep the pre-split logger name so log records are unchanged.
logger = logging.getLogger("agency_swarm.integrations.fastapi_utils.endpoint_handlers")


ReasoningEffortValue = Literal["none", "minimal", "low", "medium", "high", "xhigh"]
ReasoningSummaryValue = Literal["auto", "concise", "detailed"]


def _apply_request_model_settings_extra_args(agent: Agent, config: ClientConfig) -> None:
    """Apply explicit UI-selected model variant settings for this request only."""
    if not config.model_settings_extra_args:
        return

    current: ModelSettings = getattr(agent, "model_settings", None) or ModelSettings()
    extra_args = dict(current.extra_args or {})
    extra_args.update(config.model_settings_extra_args)

    uses_litellm = _agent_uses_litellm(agent)
    model_name = _request_model_name(agent)
    litellm_model_name = _normalize_litellm_model_name(model_name).lower() if uses_litellm else ""
    variant_model_name = litellm_model_name or model_name.lower()
    is_gateway_provider_variant = _is_gateway_provider_variant(uses_litellm, variant_model_name)

    include = extra_args.pop("include", None)
    if isinstance(include, list) and not uses_litellm and not is_gateway_provider_variant:
        existing_include = list(current.response_include or [])
        current.response_include = [*existing_include, *include]
    elif include is not None and not is_gateway_provider_variant:
        extra_args["include"] = include

    reasoning_effort = extra_args.get("reasoning_effort")
    reasoning_summary = extra_args.get("reasoning_summary")
    has_anthropic_thinking_budget = False
    is_gemini = variant_model_name.startswith(("google/", "gemini/", "vertex_ai/"))
    if variant_model_name.startswith("anthropic/"):
        _normalize_anthropic_litellm_variant_args(extra_args)
        reasoning_effort = extra_args.get("reasoning_effort")
        reasoning_summary = extra_args.get("reasoning_summary")
        has_anthropic_thinking_budget = _has_enabled_thinking_budget(extra_args)
    elif variant_model_name.startswith("xai/"):
        _normalize_xai_litellm_variant_args(extra_args, variant_model_name)
        reasoning_effort = extra_args.get("reasoning_effort")
        reasoning_summary = extra_args.get("reasoning_summary")
    elif is_gemini:
        requested_reasoning_summary = reasoning_summary
        _normalize_gemini_litellm_variant_args(extra_args)
        reasoning_effort = extra_args.get("reasoning_effort")
        reasoning_summary = requested_reasoning_summary if isinstance(requested_reasoning_summary, str) else "auto"

    normalized_effort = _reasoning_effort_value(reasoning_effort)
    normalized_summary = _reasoning_summary_value(reasoning_summary)
    is_litellm_openai = uses_litellm and _is_openai_model_name(litellm_model_name)
    if normalized_effort is None and reasoning_effort is None and has_anthropic_thinking_budget:
        normalized_effort = "high"
    if normalized_effort is not None and is_litellm_openai:
        current.reasoning = None
        if normalized_summary is not None:
            extra_args["reasoning_effort"] = {"effort": normalized_effort, "summary": normalized_summary}
        else:
            extra_args["reasoning_effort"] = normalized_effort
        extra_args.pop("reasoning_summary", None)
    elif normalized_effort is not None and (
        not uses_litellm or litellm_model_name.startswith(("anthropic/", "gemini/", "vertex_ai/"))
    ):
        current.reasoning = Reasoning(
            effort=normalized_effort,
            summary=None if uses_litellm else normalized_summary,
        )
        if not uses_litellm or is_gemini:
            extra_args.pop("reasoning_effort", None)
            extra_args.pop("reasoning_summary", None)
    elif normalized_effort is not None and uses_litellm:
        current.reasoning = None
    elif normalized_summary is not None and not uses_litellm:
        current.reasoning = Reasoning(
            effort=current.reasoning.effort if current.reasoning is not None else None,
            summary=normalized_summary,
        )
        extra_args.pop("reasoning_summary", None)
    elif isinstance(extra_args.get("reasoning"), dict) and not uses_litellm:
        raw_reasoning = cast(dict[str, Any], extra_args.pop("reasoning"))
        effort = raw_reasoning.get("effort")
        summary = raw_reasoning.get("summary")
        normalized_effort = _reasoning_effort_value(effort)
        normalized_summary = _reasoning_summary_value(summary)
        if normalized_effort is not None or normalized_summary is not None:
            current.reasoning = Reasoning(
                effort=normalized_effort,
                summary=normalized_summary,
            )
    elif isinstance(reasoning_summary, str) and isinstance(reasoning_effort, dict) and not uses_litellm:
        reasoning_effort.setdefault("summary", reasoning_summary)
        extra_args.pop("reasoning_summary", None)
    elif uses_litellm:
        extra_args.pop("reasoning_summary", None)

    if is_gateway_provider_variant:
        _move_gateway_variant_extra_args(extra_args)

    extra_body = extra_args.pop("extra_body", None)
    if isinstance(extra_body, dict) or isinstance(current.extra_body, dict):
        current_body = dict(current.extra_body) if isinstance(current.extra_body, dict) else {}
        if isinstance(extra_body, dict):
            current_body.update(extra_body)
        body_reasoning = current_body.pop("reasoning", None) if not uses_litellm else None
        if isinstance(body_reasoning, dict):
            normalized_effort = _reasoning_effort_value(body_reasoning.get("effort"))
            normalized_summary = _reasoning_summary_value(body_reasoning.get("summary"))
            if normalized_effort is not None or normalized_summary is not None:
                current.reasoning = Reasoning(effort=normalized_effort, summary=normalized_summary)
                extra_args.pop("reasoning_effort", None)
                extra_args.pop("reasoning_summary", None)
        current.extra_body = current_body or None
    max_tokens = extra_args.pop("max_tokens", None)
    if isinstance(max_tokens, int):
        current.max_tokens = max_tokens

    current.extra_args = extra_args or None
    agent.model_settings = current


def _request_model_name(agent: Agent) -> str:
    model = agent.model
    if isinstance(model, str):
        name = model
    elif isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        name = model.model
    elif _LITELLM_AVAILABLE and LitellmModel is not None and isinstance(model, LitellmModel):
        name = model.model
    elif isinstance(model, Model):
        name = getattr(model, "model", "")
    else:
        name = ""
    return name if isinstance(name, str) else ""


def _is_gateway_provider_variant(uses_litellm: bool, model_name: str) -> bool:
    if uses_litellm or "/" not in model_name:
        return False
    return not model_name.startswith(("openai/", "azure/", "azure_ai/"))


def _move_gateway_variant_extra_args(extra_args: dict[str, Any]) -> None:
    provider_keys = {
        "effort",
        "includeThoughts",
        "reasoning_effort",
        "reasoning_summary",
        "thinking",
        "thinkingBudget",
        "thinkingConfig",
        "thinkingLevel",
    }
    body = extra_args.pop("extra_body", None)
    extra_body = dict(body) if isinstance(body, dict) else {}
    for key in provider_keys:
        if key in extra_args:
            extra_body[key] = extra_args.pop(key)
    if extra_body:
        extra_args["extra_body"] = extra_body


def _reasoning_effort_value(value: object) -> ReasoningEffortValue | None:
    if isinstance(value, str) and value in {"none", "minimal", "low", "medium", "high", "xhigh"}:
        return cast(ReasoningEffortValue, value)
    return None


def _reasoning_summary_value(value: object) -> ReasoningSummaryValue | None:
    if isinstance(value, str) and value in {"auto", "concise", "detailed"}:
        return cast(ReasoningSummaryValue, value)
    return None


def _normalize_anthropic_litellm_variant_args(extra_args: dict[str, Any]) -> None:
    """Convert OpenCode Anthropic variant fields to LiteLLM-supported request params."""
    effort = extra_args.pop("effort", None)
    if isinstance(effort, str) and "reasoning_effort" not in extra_args:
        extra_args["reasoning_effort"] = effort
    extra_args.pop("reasoning_summary", None)
    extra_args.pop("include", None)
    _normalize_thinking_budget_tokens(extra_args)


def _normalize_xai_litellm_variant_args(extra_args: dict[str, Any], model_name: str) -> None:
    """Keep only xAI reasoning fields that LiteLLM forwards to Grok chat."""
    effort = extra_args.pop("effort", None)
    if _xai_litellm_model_supports_reasoning_effort(model_name):
        if isinstance(effort, str) and "reasoning_effort" not in extra_args:
            extra_args["reasoning_effort"] = effort
    else:
        extra_args.pop("reasoning_effort", None)
    extra_args.pop("reasoning_summary", None)
    extra_args.pop("include", None)


def _xai_litellm_model_supports_reasoning_effort(model_name: str) -> bool:
    try:
        import litellm

        return bool(litellm.supports_reasoning(model=model_name))
    except Exception:
        model = model_name.removeprefix("xai/").lower()
        if "non-reasoning" in model:
            return False
        return (
            "grok-3-mini" in model
            or "grok-4.3" in model
            or "grok-4-3" in model
            or "grok-4-1-fast" in model
            or "grok-code-fast" in model
        )


def _normalize_gemini_litellm_variant_args(extra_args: dict[str, Any]) -> None:
    """Convert OpenCode Gemini thinkingConfig variants to LiteLLM-supported request params."""
    thinking_config = extra_args.pop("thinkingConfig", None)
    if isinstance(thinking_config, dict):
        thinking_budget = thinking_config.get("thinkingBudget")
        thinking_level = thinking_config.get("thinkingLevel")
        if isinstance(thinking_budget, int):
            extra_args["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
            extra_args.pop("reasoning_effort", None)
        elif isinstance(thinking_level, str) and "reasoning_effort" not in extra_args:
            extra_args["reasoning_effort"] = thinking_level
    thinking_level = extra_args.pop("thinkingLevel", None)
    if isinstance(thinking_level, str) and "reasoning_effort" not in extra_args:
        extra_args["reasoning_effort"] = thinking_level
    thinking_budget = extra_args.pop("thinkingBudget", None)
    if isinstance(thinking_budget, int):
        extra_args["thinking"] = {"type": "enabled", "budget_tokens": thinking_budget}
        extra_args.pop("reasoning_effort", None)
    extra_args.pop("includeThoughts", None)
    extra_args.pop("reasoning_summary", None)
    extra_args.pop("include", None)


def _normalize_thinking_budget_tokens(extra_args: dict[str, Any]) -> None:
    thinking = extra_args.get("thinking")
    if not isinstance(thinking, dict):
        return
    budget_tokens = thinking.get("budgetTokens")
    if isinstance(budget_tokens, int) and "budget_tokens" not in thinking:
        normalized = dict(thinking)
        normalized["budget_tokens"] = budget_tokens
        normalized.pop("budgetTokens", None)
        extra_args["thinking"] = normalized


def _has_enabled_thinking_budget(extra_args: dict[str, Any]) -> bool:
    thinking = extra_args.get("thinking")
    if not isinstance(thinking, dict) or thinking.get("type") != "enabled":
        return False
    return isinstance(thinking.get("budget_tokens"), int)


def _litellm_model_name(agent: Agent) -> str:
    if not _agent_uses_litellm(agent):
        return ""
    model = agent.model
    if isinstance(model, str):
        name = model
    elif isinstance(model, OpenAIResponsesModel | OpenAIChatCompletionsModel):
        name = model.model
    elif _LITELLM_AVAILABLE and LitellmModel is not None and isinstance(model, LitellmModel):
        name = model.model
    elif isinstance(model, Model):
        name = getattr(model, "model", "")
    else:
        name = ""
    if not isinstance(name, str):
        return ""
    return _normalize_litellm_model_name(name).lower()
