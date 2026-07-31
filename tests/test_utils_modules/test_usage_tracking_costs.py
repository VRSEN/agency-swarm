from types import SimpleNamespace
from typing import cast

import pytest
from agents.items import ModelResponse
from agents.result import RunResult
from agents.usage import Usage
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from agency_swarm.utils import usage_tracking
from agency_swarm.utils.usage_tracking import UsageStats, calculate_openai_cost, calculate_usage_with_cost


def _single_request_stats(input_tokens: int, output_tokens: int) -> UsageStats:
    return UsageStats(
        request_count=1,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def _run_result_with_usage(usage: Usage, model_name: str) -> RunResult:
    response = ModelResponse(output=[], usage=usage, response_id=None)
    return cast(
        RunResult,
        SimpleNamespace(
            raw_responses=[response],
            _sub_agent_responses_with_model=[],
            _main_agent_model=model_name,
        ),
    )


def test_calculate_usage_with_cost_prices_luna_tiers_per_request() -> None:
    pricing_data = {
        "gpt-5.6-luna": {
            "input_cost_per_token": 1e-6,
            "input_cost_per_token_above_272k_tokens": 2e-6,
            "output_cost_per_token": 6e-6,
            "output_cost_per_token_above_272k_tokens": 9e-6,
        }
    }
    usage_stats = _single_request_stats(150_000, 1_000) + _single_request_stats(150_000, 1_000)

    aggregate_cost = calculate_openai_cost(
        "gpt-5.6-luna",
        input_tokens=usage_stats.input_tokens,
        output_tokens=usage_stats.output_tokens,
        pricing_data=pricing_data,
    )
    result = calculate_usage_with_cost(
        usage_stats,
        model_name="gpt-5.6-luna",
        pricing_data=pricing_data,
    )

    assert aggregate_cost == pytest.approx(0.618)
    assert result.total_cost == pytest.approx(0.312)
    assert result.total_cost < aggregate_cost


def test_calculate_usage_with_cost_rejects_ambiguous_tiered_aggregate() -> None:
    pricing_data = {
        "test/tiered": {
            "input_cost_per_token": 1.0,
            "input_cost_per_token_above_100k_tokens": 2.0,
            "output_cost_per_token": 1.0,
        }
    }
    usage_stats = UsageStats(
        request_count=2,
        input_tokens=150_000,
        output_tokens=2,
        total_tokens=150_002,
    )

    with pytest.raises(ValueError, match="per-request token breakdown"):
        calculate_usage_with_cost(usage_stats, model_name="test/tiered", pricing_data=pricing_data)


def test_cache_write_tokens_use_loaded_creation_price_when_reported(tmp_path, monkeypatch) -> None:
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(
        """
        {
          "test/cache-write": {
            "input_cost_per_token": 1.0,
            "output_cost_per_token": 0.0,
            "cache_creation_input_token_cost": 3.0,
            "cache_creation_input_token_cost_above_100k_tokens": 5.0
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(usage_tracking, "PRICING_FILE_PATH", pricing_file)
    monkeypatch.setattr(usage_tracking, "_PRICING_DATA_CACHE", None)
    pricing_data = usage_tracking.load_pricing_data()
    model_pricing = pricing_data["test/cache-write"]
    assert (
        model_pricing["cache_creation_input_token_cost_above_100k_tokens"]
        > model_pricing["cache_creation_input_token_cost"]
    )

    reported_details = InputTokensDetails.model_validate({"cached_tokens": 0, "cache_write_tokens": 50_000})
    reported_usage = Usage(
        requests=1,
        input_tokens=150_000,
        output_tokens=0,
        total_tokens=150_000,
        input_tokens_details=reported_details,
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )
    reported = calculate_usage_with_cost(
        _single_request_stats(150_000, 0),
        pricing_data=pricing_data,
        run_result=_run_result_with_usage(reported_usage, "test/cache-write"),
    )

    unreported_usage = Usage(
        requests=1,
        input_tokens=150_000,
        output_tokens=0,
        total_tokens=150_000,
        input_tokens_details=InputTokensDetails(cached_tokens=0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )
    unreported = calculate_usage_with_cost(
        _single_request_stats(150_000, 0),
        pricing_data=pricing_data,
        run_result=_run_result_with_usage(unreported_usage, "test/cache-write"),
    )

    expected_reported = 100_000 * model_pricing["input_cost_per_token"]
    expected_reported += 50_000 * model_pricing["cache_creation_input_token_cost_above_100k_tokens"]
    assert reported.total_cost == pytest.approx(expected_reported)
    assert unreported.total_cost == pytest.approx(150_000 * model_pricing["input_cost_per_token"])
    assert reported.total_cost > unreported.total_cost
