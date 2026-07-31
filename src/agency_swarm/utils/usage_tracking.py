"""Track and price model token usage."""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import NotRequired, Protocol, TypedDict, cast

from agents.items import ModelResponse
from agents.result import RunResultBase
from agents.usage import RequestUsage, Usage
from openai.types.responses.response_usage import InputTokensDetails

logger = logging.getLogger(__name__)

PRICING_FILE_PATH = Path(__file__).parent.parent / "data" / "model_prices_and_context_window.json"

PricingData = dict[str, dict[str, float]]

_PRICING_DATA_CACHE: PricingData | None = None
_PRICING_DATA_LOCK = Lock()
_BASE_PRICING_KEYS = (
    "input_cost_per_token",
    "output_cost_per_token",
    "cache_read_input_token_cost",
    "cache_creation_input_token_cost",
    "output_cost_per_reasoning_token",
)
_TIERED_PRICING_KEY = re.compile(r"^(?P<base_key>.+)_above_(?P<threshold>\d+)k_tokens$")


class UsageStatsDict(TypedDict):
    request_count: int
    cached_tokens: int
    cache_write_tokens: NotRequired[int]
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


@dataclass(frozen=True)
class RequestUsageStats:
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int | None = None


@dataclass
class UsageStats:
    """Aggregated usage with any available per-request breakdown."""

    request_count: int = 0
    cached_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    reasoning_tokens: int | None = None
    audio_tokens: int | None = None
    cache_write_tokens: int = 0
    request_usage_entries: list[RequestUsageStats] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.request_count == 1 and not self.request_usage_entries:
            self.request_usage_entries.append(
                RequestUsageStats(
                    input_tokens=self.input_tokens,
                    output_tokens=self.output_tokens,
                    cached_tokens=self.cached_tokens,
                    cache_write_tokens=self.cache_write_tokens,
                    reasoning_tokens=self.reasoning_tokens,
                )
            )

    def __add__(self, other: "UsageStats") -> "UsageStats":
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
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            request_usage_entries=self.request_usage_entries + other.request_usage_entries,
        )

    def to_dict(self) -> UsageStatsDict:
        result: UsageStatsDict = {
            "request_count": self.request_count,
            "cached_tokens": self.cached_tokens,
            "cache_write_tokens": self.cache_write_tokens,
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


class UsageCostCalculationError(ValueError):
    """Raised when aggregate usage cannot be priced accurately."""


def load_pricing_data() -> PricingData:
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
            year, month, day = parts[-3], parts[-2], parts[-1]
            if len(year) == 4 and year.isdigit() and month.isdigit() and day.isdigit():
                base_name = "-".join(parts[:-3])
                if base_name in pricing_data:
                    return pricing_data[base_name]

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
    cache_write_tokens: int = 0,
) -> float:
    """Price one model request, selecting tiers by that request's input size."""
    if pricing_data is None:
        pricing_data = load_pricing_data()

    model_pricing = get_model_pricing(model_name, pricing_data)
    if not model_pricing:
        logger.debug(f"No pricing data found for model {model_name}")
        return 0.0

    input_cost_per_token = _get_token_price(model_pricing, "input_cost_per_token", input_tokens)
    output_cost_per_token = _get_token_price(model_pricing, "output_cost_per_token", input_tokens)
    non_cached_input = max(0, input_tokens - cached_tokens - cache_write_tokens)
    cost = non_cached_input * input_cost_per_token

    cache_read_cost_per_token = _get_token_price(
        model_pricing,
        "cache_read_input_token_cost",
        input_tokens,
        input_cost_per_token,
    )
    if cached_tokens > 0:
        cost += cached_tokens * cache_read_cost_per_token

    cache_write_cost_per_token = _get_token_price(
        model_pricing,
        "cache_creation_input_token_cost",
        input_tokens,
        input_cost_per_token,
    )
    if cache_write_tokens > 0:
        cost += cache_write_tokens * cache_write_cost_per_token

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


def _cache_write_tokens(input_details: InputTokensDetails) -> int:
    cache_write_tokens = input_details.model_dump().get("cache_write_tokens")
    return cache_write_tokens if isinstance(cache_write_tokens, int) else 0


def _request_usage_stats(usage: RequestUsage) -> RequestUsageStats:
    return RequestUsageStats(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_tokens=usage.input_tokens_details.cached_tokens,
        cache_write_tokens=_cache_write_tokens(usage.input_tokens_details),
        reasoning_tokens=usage.output_tokens_details.reasoning_tokens or None,
    )


def _usage_stats_from_sdk(usage: Usage) -> UsageStats:
    return UsageStats(
        request_count=usage.requests,
        cached_tokens=usage.input_tokens_details.cached_tokens,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
        reasoning_tokens=usage.output_tokens_details.reasoning_tokens or None,
        cache_write_tokens=_cache_write_tokens(usage.input_tokens_details),
        request_usage_entries=[_request_usage_stats(entry) for entry in usage.request_usage_entries],
    )


def extract_usage_from_run_result(run_result: RunResultBase | None) -> UsageStats | None:
    """Extract aggregated and per-request usage from a run result."""
    if run_result is None or not hasattr(run_result, "context_wrapper") or run_result.context_wrapper is None:
        return None

    try:
        usage_stats = _usage_stats_from_sdk(run_result.context_wrapper.usage)
    except (AttributeError, TypeError):
        return None

    if hasattr(run_result, "_sub_agent_responses_with_model"):
        sub_agent_responses = cast(_HasSubAgentResponsesWithModel, run_result)._sub_agent_responses_with_model
        for item in sub_agent_responses:
            try:
                if isinstance(item, tuple) and len(item) == 2:
                    _, response = item
                    usage_stats += _usage_stats_from_sdk(response.usage)
            except Exception:
                pass  # Skip malformed entries

    return usage_stats


def _has_complete_request_breakdown(usage_stats: UsageStats) -> bool:
    entries = usage_stats.request_usage_entries
    return len(entries) == usage_stats.request_count and (
        sum(entry.input_tokens for entry in entries) == usage_stats.input_tokens
        and sum(entry.output_tokens for entry in entries) == usage_stats.output_tokens
        and sum(entry.cached_tokens for entry in entries) == usage_stats.cached_tokens
        and sum(entry.cache_write_tokens for entry in entries) == usage_stats.cache_write_tokens
        and (
            usage_stats.reasoning_tokens is None
            or sum(entry.reasoning_tokens or 0 for entry in entries) == usage_stats.reasoning_tokens
        )
    )


def _tier_boundary_is_ambiguous(
    usage_stats: UsageStats,
    model_name: str,
    pricing_data: PricingData | None,
) -> bool:
    model_pricing = get_model_pricing(model_name, pricing_data)
    if model_pricing is None:
        return False
    priced_tokens = {
        "input_cost_per_token": max(
            0,
            usage_stats.input_tokens - usage_stats.cached_tokens - usage_stats.cache_write_tokens,
        ),
        "output_cost_per_token": usage_stats.output_tokens,
        "cache_read_input_token_cost": usage_stats.cached_tokens,
        "cache_creation_input_token_cost": usage_stats.cache_write_tokens,
        "output_cost_per_reasoning_token": usage_stats.reasoning_tokens or 0,
    }
    for tier_key in model_pricing:
        match = _TIERED_PRICING_KEY.fullmatch(tier_key)
        if match is None or priced_tokens.get(match.group("base_key"), 0) == 0:
            continue
        if int(match.group("threshold")) * 1000 < usage_stats.input_tokens:
            return True
    return False


def _calculate_usage_cost(
    usage_stats: UsageStats,
    model_name: str,
    pricing_data: PricingData | None,
) -> float:
    if _has_complete_request_breakdown(usage_stats):
        return sum(
            calculate_openai_cost(
                model_name=model_name,
                input_tokens=entry.input_tokens,
                output_tokens=entry.output_tokens,
                cached_tokens=entry.cached_tokens,
                reasoning_tokens=entry.reasoning_tokens,
                pricing_data=pricing_data,
                cache_write_tokens=entry.cache_write_tokens,
            )
            for entry in usage_stats.request_usage_entries
        )
    if usage_stats.request_count > 1 and _tier_boundary_is_ambiguous(usage_stats, model_name, pricing_data):
        raise UsageCostCalculationError(
            f"Cannot calculate tiered cost for {usage_stats.request_count} aggregated requests "
            "without a complete per-request token breakdown."
        )
    return calculate_openai_cost(
        model_name=model_name,
        input_tokens=usage_stats.input_tokens,
        output_tokens=usage_stats.output_tokens,
        cached_tokens=usage_stats.cached_tokens,
        reasoning_tokens=usage_stats.reasoning_tokens,
        pricing_data=pricing_data,
        cache_write_tokens=usage_stats.cache_write_tokens,
    )


def calculate_usage_with_cost(
    usage_stats: UsageStats,
    model_name: str | None = None,
    pricing_data: PricingData | None = None,
    run_result: RunResultBase | None = None,
) -> UsageStats:
    """Add per-request cost to usage statistics."""
    if model_name is None and run_result is not None and hasattr(run_result, "_main_agent_model"):
        model_name = cast(_HasMainAgentModel, run_result)._main_agent_model

    if run_result:
        total_cost = 0.0
        calculated_any = False

        def _calculate_response_cost(response: ModelResponse, resp_model_name: str | None) -> float:
            if not resp_model_name:
                return 0.0

            return _calculate_usage_cost(_usage_stats_from_sdk(response.usage), resp_model_name, pricing_data)

        for response in run_result.raw_responses:
            try:
                response_cost = _calculate_response_cost(response, model_name)
                if response_cost > 0:
                    total_cost += response_cost
                    calculated_any = True
            except UsageCostCalculationError:
                raise
            except Exception as e:
                logger.debug(f"Could not calculate cost for main agent response: {e}")

        if hasattr(run_result, "_sub_agent_responses_with_model"):
            sub_agent_responses = cast(_HasSubAgentResponsesWithModel, run_result)._sub_agent_responses_with_model
            for item in sub_agent_responses:
                try:
                    if isinstance(item, tuple) and len(item) == 2:
                        sub_model_name, response = item
                        response_cost = _calculate_response_cost(response, sub_model_name)
                        if response_cost > 0:
                            total_cost += response_cost
                            calculated_any = True
                except UsageCostCalculationError:
                    raise
                except Exception as e:
                    logger.debug(f"Could not calculate cost for sub-agent response: {e}")

        if calculated_any:
            usage_stats.total_cost = total_cost
            return usage_stats

    if model_name:
        actual_model_name = model_name
        if "/" in model_name:
            parts = model_name.split("/")
            if len(parts) > 1:
                actual_model_name = "/".join(parts[-2:]) if len(parts) > 2 else parts[-1]

        cost = _calculate_usage_cost(usage_stats, actual_model_name, pricing_data)

        if cost == 0.0 and model_name != actual_model_name:  # noqa: PLR2004
            cost = _calculate_usage_cost(usage_stats, model_name, pricing_data)

        usage_stats.total_cost = cost
    else:
        logger.debug("No model name available for cost calculation")
        usage_stats.total_cost = 0.0

    return usage_stats


def format_usage_for_display(usage_stats: UsageStats, model_name: str | None = None) -> str:
    lines = [f"Requests: {usage_stats.request_count}", "Tokens:", f"  Input: {usage_stats.input_tokens:,}"]
    if model_name:
        lines.insert(0, f"Model: {model_name}")
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
