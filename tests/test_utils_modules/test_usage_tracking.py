from __future__ import annotations

from types import SimpleNamespace

import pytest

from agency_swarm.utils.usage_tracking import UsageStats, calculate_usage_with_cost, extract_usage_from_run_result


def test_extract_usage_from_run_result_returns_none_without_context_wrapper() -> None:
    run_result = SimpleNamespace(context_wrapper=None)
    assert extract_usage_from_run_result(run_result) is None


def test_extract_usage_from_run_result_reads_requests_and_tokens() -> None:
    usage = SimpleNamespace(
        requests=2,
        cached_tokens=3,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        input_tokens_details=None,
        output_tokens_details=None,
    )
    run_result = SimpleNamespace(context_wrapper=SimpleNamespace(usage=usage))

    stats = extract_usage_from_run_result(run_result)
    assert stats == UsageStats(
        request_count=2,
        cached_tokens=3,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        total_cost=0.0,
        reasoning_tokens=None,
        audio_tokens=None,
    )


def test_extract_usage_from_run_result_extracts_reasoning_and_sums_subagent_reasoning() -> None:
    main_usage = SimpleNamespace(
        requests=1,
        cached_tokens=0,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        input_tokens_details=SimpleNamespace(reasoning_tokens=5, audio_tokens=None),
        output_tokens_details=None,
    )

    # Sub-agent response usage is an object (not a dict), so reasoning extraction path runs.
    sub_usage = SimpleNamespace(
        requests=1,
        cached_tokens=0,
        input_tokens=1,
        output_tokens=2,
        total_tokens=3,
        input_tokens_details=SimpleNamespace(reasoning_tokens=7),
        output_tokens_details=None,
    )
    sub_response = SimpleNamespace(usage=sub_usage)

    run_result = SimpleNamespace(
        context_wrapper=SimpleNamespace(usage=main_usage),
        _sub_agent_responses_with_model=[("gpt-4o", sub_response)],
    )

    stats = extract_usage_from_run_result(run_result)
    assert stats is not None
    assert stats.request_count == 2
    assert stats.input_tokens == 11
    assert stats.output_tokens == 22
    assert stats.total_tokens == 33
    assert stats.reasoning_tokens == 12  # 5 main + 7 sub


def test_extract_usage_from_run_result_aggregates_subagent_usage_dict_with_fallback_requests() -> None:
    main_usage = SimpleNamespace(
        requests=0,
        cached_tokens=0,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        input_tokens_details=None,
        output_tokens_details=None,
    )

    # For dict usage, helper defaults requests to 1 if neither requests nor request_count are present.
    sub_response = SimpleNamespace(
        usage={
            "input_tokens": 4,
            "output_tokens": 6,
            "total_tokens": 10,
        }
    )

    run_result = SimpleNamespace(
        context_wrapper=SimpleNamespace(usage=main_usage),
        _sub_agent_responses_with_model=[("gpt-4o", sub_response)],
    )

    stats = extract_usage_from_run_result(run_result)
    assert stats is not None
    assert stats.request_count == 1
    assert stats.input_tokens == 4
    assert stats.output_tokens == 6
    assert stats.total_tokens == 10


def test_calculate_usage_with_cost_per_response_costs_all_token_types() -> None:
    """
    Single per-response costing test that verifies:
    - input token pricing
    - cached input token pricing (via input_tokens_details.cached_tokens)
    - output token pricing
    - reasoning token pricing (via output_tokens_details.reasoning_tokens)
    """
    pricing_data = {
        "test/all-tokens-model": {
            "input_cost_per_token": 1.0,
            "cache_read_input_token_cost": 0.1,
            "output_cost_per_token": 2.0,
            "output_cost_per_reasoning_token": 0.01,
        }
    }

    response_usage = SimpleNamespace(
        input_tokens=10,
        output_tokens=3,
        cached_tokens=0,  # simulate missing top-level cached_tokens
        input_tokens_details=SimpleNamespace(cached_tokens=4),
        output_tokens_details=SimpleNamespace(reasoning_tokens=5),
    )
    response = SimpleNamespace(usage=response_usage)

    run_result = SimpleNamespace(raw_responses=[response], _main_agent_model="test/all-tokens-model")

    base = UsageStats(
        request_count=1,
        cached_tokens=0,
        input_tokens=10,
        output_tokens=3,
        total_tokens=13,
        total_cost=0.0,
        reasoning_tokens=None,
        audio_tokens=None,
    )

    with_cost = calculate_usage_with_cost(base, pricing_data=pricing_data, run_result=run_result)

    # (10 - 4)*1.0 + 4*0.1 + 3*2.0 + 5*0.01 = 6 + 0.4 + 6 + 0.05 = 12.45
    assert with_cost.total_cost == pytest.approx(12.45)

