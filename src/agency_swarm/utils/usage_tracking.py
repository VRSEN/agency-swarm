"""
Usage tracking utilities for Agency Swarm.

This module provides functions to track and calculate token usage and costs
for both OpenAI and LiteLLM models.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import NotRequired, Protocol, TypedDict, cast

from agents.items import ModelResponse
from agents.result import RunResultBase

logger = logging.getLogger(__name__)

# Path to the pricing JSON file
PRICING_FILE_PATH = Path(__file__).parent.parent / "data" / "model_prices_and_context_window.json"

PricingData = dict[str, dict[str, float]]

_PRICING_DATA_CACHE: PricingData | None = None
_PRICING_DATA_LOCK = Lock()


class UsageStatsDict(TypedDict):
    request_count: int
    cached_tokens: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    total_cost: float
    reasoning_tokens: NotRequired[int]
    audio_tokens: NotRequired[int]


def _coerce_price(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


class _HasSubAgentResponsesWithModel(Protocol):
    _sub_agent_responses_with_model: list[tuple[str | None, ModelResponse]]


class _HasMainAgentModel(Protocol):
    _main_agent_model: str


@dataclass
class UsageStats:
    """Usage statistics for a run or session."""

    request_count: int = 0
    cached_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    # Additional fields from Responses API
    reasoning_tokens: int | None = None
    audio_tokens: int | None = None

    def __add__(self, other: "UsageStats") -> "UsageStats":
        """Merge two UsageStats objects."""
        return UsageStats(
            request_count=self.request_count + other.request_count,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            total_cost=self.total_cost + other.total_cost,
            reasoning_tokens=(
                (self.reasoning_tokens or 0) + (other.reasoning_tokens or 0)
                if self.reasoning_tokens is not None or other.reasoning_tokens is not None
                else None
            ),
            audio_tokens=(
                (self.audio_tokens or 0) + (other.audio_tokens or 0)
                if self.audio_tokens is not None or other.audio_tokens is not None
                else None
            ),
        )

    def to_dict(self) -> UsageStatsDict:
        """Convert to dictionary for JSON serialization."""
        result: UsageStatsDict = {
            "request_count": self.request_count,
            "cached_tokens": self.cached_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
        }
        if self.reasoning_tokens is not None:
            result["reasoning_tokens"] = self.reasoning_tokens
        if self.audio_tokens is not None:
            result["audio_tokens"] = self.audio_tokens
        return result


def load_pricing_data() -> PricingData:
    """Load pricing data from the JSON file."""
    global _PRICING_DATA_CACHE
    with _PRICING_DATA_LOCK:
        if _PRICING_DATA_CACHE is not None:
            return _PRICING_DATA_CACHE

        if not PRICING_FILE_PATH.exists():
            logger.warning(f"Pricing file not found at {PRICING_FILE_PATH}. Cost calculation will be unavailable.")
            return {}

        try:
            with open(PRICING_FILE_PATH, encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load pricing data: {e}")
            return {}

        if not isinstance(raw, dict):
            return {}

        pricing_data: PricingData = {}
        for model_name, model_pricing in raw.items():
            if not isinstance(model_name, str) or not isinstance(model_pricing, dict):
                continue
            pricing_data[model_name] = {
                "input_cost_per_token": _coerce_price(model_pricing.get("input_cost_per_token")),
                "output_cost_per_token": _coerce_price(model_pricing.get("output_cost_per_token")),
                "cache_read_input_token_cost": _coerce_price(model_pricing.get("cache_read_input_token_cost")),
                "output_cost_per_reasoning_token": _coerce_price(model_pricing.get("output_cost_per_reasoning_token")),
            }

        _PRICING_DATA_CACHE = pricing_data
        return _PRICING_DATA_CACHE


def get_model_pricing(model_name: str, pricing_data: PricingData | None = None) -> dict[str, float] | None:
    """Get pricing information for a specific model.

    Handles model name variations and provider prefixes:
    - Exact match first (e.g., "azure/gpt-4o", "gpt-4o", "gpt-5")
    - Models without prefixes (e.g., "gpt-5") are matched directly via exact match
    - For provider-prefixed models (e.g., "azure/gpt-4o"), tries base name as fallback
    - For versioned models, tries base name (e.g., "gpt-4o-2024-05-13" -> "gpt-4o")

    This ensures correct pricing for:
    - Models without provider prefixes (e.g., "gpt-5", "gpt-4o") - matched directly
    - Provider-specific models (e.g., "azure/gpt-4o") - matched with prefix, falls back to base
    - Versioned models - matched with version, falls back to base model
    """
    if pricing_data is None:
        pricing_data = load_pricing_data()

    # Try exact match first (handles both "azure/gpt-4o" and "gpt-4o")
    if model_name in pricing_data:
        return pricing_data[model_name]

    # Handle provider prefixes (e.g., "azure/gpt-4o", "openai/gpt-4o")
    # If provider prefix is present, try exact match first, then fall back to base name
    if "/" in model_name:
        parts = model_name.split("/")
        base_name = parts[-1]

        # If exact match with provider prefix exists, use it
        # Otherwise, fall back to base name (e.g., "azure/gpt-4o" not found -> try "gpt-4o")
        if base_name in pricing_data:
            return pricing_data[base_name]

        # Continue with base_name for version/date handling below
        model_name = base_name

    # For versioned models, try base name (e.g., "gpt-4o-2024-05-13" -> "gpt-4o")
    # Split on date pattern (YYYY-MM-DD) or just take first part before last dash
    if "-" in model_name:
        # Try removing date suffix (format: model-YYYY-MM-DD)
        parts = model_name.split("-")
        if len(parts) >= 4:
            # Check if last 3 parts look like a date (YYYY-MM-DD)
            try:
                year, month, day = parts[-3], parts[-2], parts[-1]
                if len(year) == 4 and year.isdigit() and month.isdigit() and day.isdigit():
                    base_name = "-".join(parts[:-3])
                    if base_name in pricing_data:
                        return pricing_data[base_name]
            except (ValueError, IndexError):
                pass

        # Fallback: try just the base model name (everything before last dash)
        # This handles cases like "gpt-4o-mini" -> try "gpt-4o" if "gpt-4o-mini" not found
        base_name = "-".join(parts[:-1])
        if base_name in pricing_data:
            return pricing_data[base_name]

    return None


def calculate_openai_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    reasoning_tokens: int | None = None,
    pricing_data: PricingData | None = None,
) -> float:
    """Calculate cost for any model based on token usage.

    Uses the LiteLLM pricing JSON format which stores costs per token for all models
    (OpenAI, LiteLLM, Azure, Anthropic, etc.):
    - input_cost_per_token: cost per input token
    - output_cost_per_token: cost per output token
    - cache_read_input_token_cost: cost per cached input token
    - output_cost_per_reasoning_token: cost per reasoning token (if available)

    Note: Despite the function name "calculate_openai_cost", this works for all models
    in the pricing JSON file, not just OpenAI models.

    Args:
        model_name: The model name (e.g., 'gpt-4o', 'gpt-4-turbo', 'anthropic/claude-sonnet-4')
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        cached_tokens: Number of cached tokens (if any)
        reasoning_tokens: Number of reasoning tokens (for o1 models)
        pricing_data: Optional pre-loaded pricing data

    Returns:
        Total cost in USD
    """
    if pricing_data is None:
        pricing_data = load_pricing_data()

    model_pricing = get_model_pricing(model_name, pricing_data)
    if not model_pricing:
        logger.debug(f"No pricing data found for model {model_name}")
        return 0.0

    cost = 0.0

    # Get per-token costs from JSON (LiteLLM format uses per-token costs)
    input_cost_per_token = model_pricing.get("input_cost_per_token", 0.0)
    output_cost_per_token = model_pricing.get("output_cost_per_token", 0.0)

    # Calculate cost for non-cached input tokens
    non_cached_input = max(0, input_tokens - cached_tokens)
    cost += non_cached_input * input_cost_per_token

    # Cached tokens typically have a different (lower) price
    # Use cache_read_input_token_cost if available, otherwise fall back to input_cost_per_token
    cache_read_cost_per_token = model_pricing.get("cache_read_input_token_cost", input_cost_per_token)
    if cached_tokens > 0:
        cost += cached_tokens * cache_read_cost_per_token

    # Output tokens
    cost += output_tokens * output_cost_per_token

    # Handle reasoning tokens (for o1 models)
    # Note: reasoning tokens might be charged differently - check for output_cost_per_reasoning_token
    if reasoning_tokens is not None and reasoning_tokens > 0:
        reasoning_cost_per_token = model_pricing.get("output_cost_per_reasoning_token", 0.0)
        if reasoning_cost_per_token > 0:
            cost += reasoning_tokens * reasoning_cost_per_token
        # If no specific reasoning token cost, they might be included in output_cost_per_token
        # In that case, we don't double-count them

    return cost


def _extract_usage_from_response(response: ModelResponse) -> dict[str, int]:
    """Extract usage data from a single response.

    Returns a dict with normalized keys: requests, cached_tokens, input_tokens, output_tokens, total_tokens
    """
    usage = response.usage
    return {
        "requests": usage.requests,
        "cached_tokens": usage.input_tokens_details.cached_tokens,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }


def extract_usage_from_run_result(run_result: RunResultBase | None) -> UsageStats | None:
    """Extract usage information from a RunResult or RunResultStreaming object.

    Aggregates usage from:
    1. Main agent via context_wrapper.usage
    2. Sub-agent responses via _sub_agent_responses_with_model

    Args:
        run_result: A RunResult or RunResultStreaming object from the agents SDK

    Returns:
        UsageStats object or None if usage information is not available
    """
    if run_result is None:
        return None

    # Initialize counters
    request_count = 0
    cached_tokens = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    reasoning_tokens = None
    audio_tokens = None  # TODO(voice): Populate when Agency Swarm adds voice/realtime support.
    found_any_usage = False

    # Extract usage from context_wrapper if available
    if hasattr(run_result, "context_wrapper") and run_result.context_wrapper is not None:
        try:
            usage = run_result.context_wrapper.usage
            found_any_usage = True

            request_count = usage.requests
            cached_tokens = usage.input_tokens_details.cached_tokens
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
            total_tokens = usage.total_tokens
            reasoning_tokens = usage.output_tokens_details.reasoning_tokens or None
        except (AttributeError, TypeError):
            # Skip if context_wrapper or usage is not accessible
            pass

    # Aggregate usage from sub-agent responses
    if hasattr(run_result, "_sub_agent_responses_with_model"):
        sub_agent_responses = cast(_HasSubAgentResponsesWithModel, run_result)._sub_agent_responses_with_model
        for item in sub_agent_responses:
            try:
                if isinstance(item, tuple) and len(item) == 2:
                    _, response = item
                    resp_usage = _extract_usage_from_response(response)
                    request_count += resp_usage.get("requests", 0)
                    cached_tokens += resp_usage.get("cached_tokens", 0)
                    input_tokens += resp_usage.get("input_tokens", 0)
                    output_tokens += resp_usage.get("output_tokens", 0)
                    total_tokens += resp_usage.get("total_tokens", 0)
                    sub_reasoning = response.usage.output_tokens_details.reasoning_tokens
                    if sub_reasoning:
                        reasoning_tokens = (reasoning_tokens or 0) + sub_reasoning
            except Exception:
                pass  # Skip malformed entries

    if not found_any_usage:
        return None

    return UsageStats(
        request_count=request_count,
        cached_tokens=cached_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        reasoning_tokens=reasoning_tokens,
        audio_tokens=audio_tokens,
    )


def calculate_usage_with_cost(
    usage_stats: UsageStats,
    model_name: str | None = None,
    pricing_data: PricingData | None = None,
    run_result: RunResultBase | None = None,
) -> UsageStats:
    """Calculate cost for usage statistics and add it to the stats.

    Uses a unified approach for all models:
    1. Calculates costs per-response using pricing data (handles multi-agent correctly)
    2. Falls back to single-model calculation using aggregated usage

    Args:
        usage_stats: Usage statistics without cost
        model_name: Optional model name for cost calculation. If not provided,
            will be extracted from run_result._main_agent_model if available.
        pricing_data: Optional pre-loaded pricing data
        run_result: Optional RunResult to extract cost from. Contains both
            main agent's raw_responses and sub-agent responses with model info.

    Returns:
        UsageStats with cost calculated
    """
    # Extract main agent's model from run_result if not explicitly provided
    if model_name is None and run_result is not None and hasattr(run_result, "_main_agent_model"):
        model_name = cast(_HasMainAgentModel, run_result)._main_agent_model

    # Try per-response costing first for multi-agent correctness.
    if run_result:
        total_cost = 0.0
        calculated_any = False

        def _calculate_response_cost(response: ModelResponse, resp_model_name: str | None) -> float:
            """Calculate cost for a single response given its model name."""
            if not resp_model_name:
                return 0.0

            response_usage = response.usage
            response_reasoning_tokens = response_usage.output_tokens_details.reasoning_tokens or None

            return calculate_openai_cost(
                model_name=resp_model_name,
                input_tokens=response_usage.input_tokens,
                output_tokens=response_usage.output_tokens,
                cached_tokens=response_usage.input_tokens_details.cached_tokens,
                reasoning_tokens=response_reasoning_tokens,
                pricing_data=pricing_data,
            )

        # Process main agent's raw_responses (use fallback model_name)
        raw_responses = run_result.raw_responses
        if len(raw_responses) > 0:
            for response in raw_responses:
                try:
                    # For main agent responses, use the provided model_name as fallback
                    response_cost = _calculate_response_cost(response, model_name)
                    if response_cost > 0:
                        total_cost += response_cost
                        calculated_any = True
                except Exception as e:
                    logger.debug(f"Could not calculate cost for main agent response: {e}")

        # Process sub-agent responses with their specific model names
        # These are stored as tuples of (model_name, response)
        if hasattr(run_result, "_sub_agent_responses_with_model"):
            sub_agent_responses = cast(_HasSubAgentResponsesWithModel, run_result)._sub_agent_responses_with_model
            if len(sub_agent_responses) > 0:
                for item in sub_agent_responses:
                    try:
                        if isinstance(item, tuple) and len(item) == 2:
                            sub_model_name, response = item
                            response_cost = _calculate_response_cost(response, sub_model_name)
                            if response_cost > 0:
                                total_cost += response_cost
                                calculated_any = True
                    except Exception as e:
                        logger.debug(f"Could not calculate cost for sub-agent response: {e}")

        if calculated_any:
            usage_stats.total_cost = total_cost
            return usage_stats

    # Fall back to single-model costing using aggregated usage.
    if model_name:
        # Handle LiteLLM model name format (e.g., "litellm/anthropic/claude-sonnet-4").
        actual_model_name = model_name
        if "/" in model_name:
            parts = model_name.split("/")
            if len(parts) > 1:
                actual_model_name = "/".join(parts[-2:]) if len(parts) > 2 else parts[-1]

        cost = calculate_openai_cost(
            model_name=actual_model_name,
            input_tokens=usage_stats.input_tokens,
            output_tokens=usage_stats.output_tokens,
            cached_tokens=usage_stats.cached_tokens,
            reasoning_tokens=usage_stats.reasoning_tokens,
            pricing_data=pricing_data,
        )

        # If cost calculation failed with model name, try with full LiteLLM path
        if cost == 0.0 and model_name != actual_model_name:  # noqa: PLR2004
            cost = calculate_openai_cost(
                model_name=model_name,
                input_tokens=usage_stats.input_tokens,
                output_tokens=usage_stats.output_tokens,
                cached_tokens=usage_stats.cached_tokens,
                reasoning_tokens=usage_stats.reasoning_tokens,
                pricing_data=pricing_data,
            )

        usage_stats.total_cost = cost
    else:
        # No model name provided and couldn't extract from responses
        logger.debug("No model name available for cost calculation")
        usage_stats.total_cost = 0.0

    return usage_stats


def format_usage_for_display(usage_stats: UsageStats, model_name: str | None = None) -> str:
    """Format usage statistics for display in terminal or logs.

    Args:
        usage_stats: Usage statistics to format
        model_name: Optional model name to include in output

    Returns:
        Formatted string
    """
    lines = []
    if model_name:
        lines.append(f"Model: {model_name}")

    lines.append(f"Requests: {usage_stats.request_count}")
    lines.append("Tokens:")
    lines.append(f"  Input: {usage_stats.input_tokens:,}")
    if usage_stats.cached_tokens > 0:
        lines.append(f"  Cached: {usage_stats.cached_tokens:,}")
    lines.append(f"  Output: {usage_stats.output_tokens:,}")
    lines.append(f"  Total: {usage_stats.total_tokens:,}")

    if usage_stats.reasoning_tokens is not None and usage_stats.reasoning_tokens > 0:
        lines.append(f"  Reasoning: {usage_stats.reasoning_tokens:,}")

    if usage_stats.audio_tokens is not None and usage_stats.audio_tokens > 0:
        lines.append(f"  Audio: {usage_stats.audio_tokens:,}")

    if usage_stats.total_cost > 0:
        lines.append(f"Cost: ${usage_stats.total_cost:.6f}")

    return "\n".join(lines)
