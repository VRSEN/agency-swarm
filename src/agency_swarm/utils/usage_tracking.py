"""
Usage tracking utilities for Agency Swarm.

This module provides functions to track and calculate token usage and costs
for both OpenAI and LiteLLM models.
"""

import json
import logging
import re
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
_BASE_PRICING_KEYS = (
    "input_cost_per_token",
    "output_cost_per_token",
    "cache_read_input_token_cost",
    "output_cost_per_reasoning_token",
)
_TIERED_PRICING_KEY = re.compile(r"^(?P<base_key>.+)_above_(?P<threshold>\d+)k_tokens$")


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
            prices = {key: _coerce_price(model_pricing.get(key)) for key in _BASE_PRICING_KEYS}
            prices.update(
                {
                    key: _coerce_price(value)
                    for key, value in model_pricing.items()
                    if isinstance(key, str) and _TIERED_PRICING_KEY.fullmatch(key)
                }
            )
            pricing_data[model_name] = prices

        _PRICING_DATA_CACHE = pricing_data
        return _PRICING_DATA_CACHE


def get_model_pricing(model_name: str, pricing_data: PricingData | None = None) -> dict[str, float] | None:
    """Resolve exact, provider-prefixed, or versioned model pricing."""
    if pricing_data is None:
        pricing_data = load_pricing_data()

    if model_name in pricing_data:
        return pricing_data[model_name]

    if "/" in model_name:
        parts = model_name.split("/")
        base_name = parts[-1]
        if base_name in pricing_data:
            return pricing_data[base_name]
        model_name = base_name

    if "-" in model_name:
        parts = model_name.split("-")
        if len(parts) >= 4:
            try:
                year, month, day = parts[-3], parts[-2], parts[-1]
                if len(year) == 4 and year.isdigit() and month.isdigit() and day.isdigit():
                    base_name = "-".join(parts[:-3])
                    if base_name in pricing_data:
                        return pricing_data[base_name]
            except (ValueError, IndexError):
                pass

        base_name = "-".join(parts[:-1])
        if base_name in pricing_data:
            return pricing_data[base_name]

    return None


def _get_token_price(
    model_pricing: dict[str, float],
    price_key: str,
    input_tokens: int,
    default: float = 0.0,
) -> float:
    selected_threshold = 0
    selected_price = model_pricing.get(price_key, default)
    for tier_key, tier_price in model_pricing.items():
        match = _TIERED_PRICING_KEY.fullmatch(tier_key)
        if match is None or match.group("base_key") != price_key:
            continue
        threshold = int(match.group("threshold")) * 1000
        if selected_threshold < threshold < input_tokens:
            selected_threshold = threshold
            selected_price = tier_price
    return selected_price


def calculate_openai_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    reasoning_tokens: int | None = None,
    pricing_data: PricingData | None = None,
) -> float:
    """Calculate per-token cost, selecting declared tiers by total input size."""
    if pricing_data is None:
        pricing_data = load_pricing_data()

    model_pricing = get_model_pricing(model_name, pricing_data)
    if not model_pricing:
        logger.debug(f"No pricing data found for model {model_name}")
        return 0.0

    input_cost_per_token = _get_token_price(model_pricing, "input_cost_per_token", input_tokens)
    output_cost_per_token = _get_token_price(model_pricing, "output_cost_per_token", input_tokens)
    non_cached_input = max(0, input_tokens - cached_tokens)
    cost = non_cached_input * input_cost_per_token

    cache_read_cost_per_token = _get_token_price(
        model_pricing,
        "cache_read_input_token_cost",
        input_tokens,
        input_cost_per_token,
    )
    if cached_tokens > 0:
        cost += cached_tokens * cache_read_cost_per_token

    cost += output_tokens * output_cost_per_token

    if reasoning_tokens is not None and reasoning_tokens > 0:
        reasoning_cost_per_token = _get_token_price(
            model_pricing,
            "output_cost_per_reasoning_token",
            input_tokens,
        )
        if reasoning_cost_per_token > 0:
            cost += reasoning_tokens * reasoning_cost_per_token

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
