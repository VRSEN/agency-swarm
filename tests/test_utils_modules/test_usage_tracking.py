from __future__ import annotations

import typing

import pytest
from agents.items import ModelResponse
from agents.result import RunResult
from agents.run_context import RunContextWrapper
from agents.usage import Usage
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from agency_swarm.agent.core import Agent
from agency_swarm.context import MasterContext
from agency_swarm.utils.thread import ThreadManager
from agency_swarm.utils.usage_tracking import UsageStats, calculate_usage_with_cost, extract_usage_from_run_result


class _HasSubAgentResponsesWithModel(typing.Protocol):
    _sub_agent_responses_with_model: list[tuple[str | None, ModelResponse]]


class _HasMainAgentModel(typing.Protocol):
    _main_agent_model: str


def _make_run_result(*, usage: Usage, raw_responses: list[ModelResponse] | None = None) -> RunResult:
    agent = Agent(name="TestAgent", instructions="Base instructions")
    thread_manager = ThreadManager()
    master_context = MasterContext(
        thread_manager=thread_manager,
        agents={agent.name: agent},
        user_context={},
        agent_runtime_state={},
        current_agent_name=agent.name,
        shared_instructions=None,
    )
    wrapper = RunContextWrapper(context=master_context, usage=usage)
    return RunResult(
        input="Hello",
        new_items=[],
        raw_responses=list(raw_responses or []),
        final_output="ok",
        input_guardrail_results=[],
        output_guardrail_results=[],
        tool_input_guardrail_results=[],
        tool_output_guardrail_results=[],
        context_wrapper=wrapper,
        _last_agent=agent,
    )


def test_extract_usage_from_run_result_returns_none_without_run_result() -> None:
    assert extract_usage_from_run_result(None) is None


def test_extract_usage_from_run_result_reads_requests_and_tokens() -> None:
    usage = Usage(
        requests=2,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        input_tokens_details=InputTokensDetails(cached_tokens=3),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )
    run_result = _make_run_result(usage=usage)

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
    main_usage = Usage(
        requests=1,
        input_tokens=10,
        output_tokens=20,
        total_tokens=30,
        input_tokens_details=InputTokensDetails(cached_tokens=0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=5),
    )

    sub_usage = Usage(
        requests=1,
        input_tokens=1,
        output_tokens=2,
        total_tokens=3,
        input_tokens_details=InputTokensDetails(cached_tokens=0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=7),
    )

    run_result = _make_run_result(usage=main_usage)
    typing.cast(_HasSubAgentResponsesWithModel, run_result)._sub_agent_responses_with_model = [
        ("gpt-4o", ModelResponse(output=[], usage=sub_usage, response_id=None))
    ]

    stats = extract_usage_from_run_result(run_result)
    assert stats is not None
    assert stats.request_count == 2
    assert stats.input_tokens == 11
    assert stats.output_tokens == 22
    assert stats.total_tokens == 33
    assert stats.reasoning_tokens == 12  # 5 main + 7 sub


def test_calculate_usage_with_cost_per_response_costs_all_token_types() -> None:
    """
    Single per-response costing test that verifies:
    - input token pricing
    - cached input token pricing (via input_tokens_details.cached_tokens)
    - output token pricing
    - reasoning token pricing (via output_tokens_details.reasoning_tokens)
    - dict-based usage (sub-agent) uses that sub-agent's model pricing
    """
    pricing_data = {
        "test/all-tokens-model": {
            "input_cost_per_token": 1.0,
            "cache_read_input_token_cost": 0.1,
            "output_cost_per_token": 2.0,
            "output_cost_per_reasoning_token": 0.01,
        }
        ,
        "test/sub-agent-model": {
            "input_cost_per_token": 10.0,
            "cache_read_input_token_cost": 1.0,
            "output_cost_per_token": 20.0,
            "output_cost_per_reasoning_token": 0.5,
        },
    }

    response_usage = Usage(
        requests=1,
        input_tokens=10,
        output_tokens=3,
        total_tokens=13,
        input_tokens_details=InputTokensDetails(cached_tokens=4),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=5),
    )
    response = ModelResponse(output=[], usage=response_usage, response_id=None)
    run_result = _make_run_result(usage=Usage(), raw_responses=[response])
    typing.cast(_HasMainAgentModel, run_result)._main_agent_model = "test/all-tokens-model"

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

    # Main response:
    # (10 - 4)*1.0 + 4*0.1 + 3*2.0 + 5*0.01 = 6 + 0.4 + 6 + 0.05 = 12.45
    assert with_cost.total_cost == pytest.approx(12.45)
