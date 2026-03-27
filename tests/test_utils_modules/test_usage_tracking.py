from __future__ import annotations

import threading
import time
import typing
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from agents import Tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ModelSettings
from agents.models.interface import Model, ModelTracing
from agents.result import RunResult
from agents.run_context import RunContextWrapper
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText
from openai.types.responses.response_prompt_param import ResponsePromptParam
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from agency_swarm.agent.core import Agent
from agency_swarm.context import MasterContext
from agency_swarm.utils import usage_tracking
from agency_swarm.utils.thread import ThreadManager
from agency_swarm.utils.usage_tracking import (
    UsageStats,
    calculate_openai_cost,
    calculate_usage_with_cost,
    extract_usage_from_run_result,
    format_usage_for_display,
    get_model_pricing,
    load_pricing_data,
)


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
        ("gpt-5.4-mini", ModelResponse(output=[], usage=sub_usage, response_id=None))
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
        },
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


@pytest.mark.asyncio
async def test_calculate_usage_with_cost_uses_model_name_from_model_instance() -> None:
    """Regression: costing should work when an Agent is configured with a Model instance."""

    class FakeModel(Model):
        def __init__(self, model: str) -> None:
            self.model = model

        async def get_response(
            self,
            system_instructions: str | None,
            input: str | list[TResponseInputItem],
            model_settings: ModelSettings,
            tools: list[Tool],
            output_schema: AgentOutputSchemaBase | None,
            handoffs: list[Handoff],
            tracing: ModelTracing,
            *,
            previous_response_id: str | None,
            conversation_id: str | None,
            prompt: ResponsePromptParam | None,
        ) -> ModelResponse:
            usage = Usage(
                requests=1,
                input_tokens=2,
                output_tokens=1,
                total_tokens=3,
                input_tokens_details=InputTokensDetails(cached_tokens=0),
                output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
            )
            msg = ResponseOutputMessage(
                id="msg_1",
                content=[ResponseOutputText(text="ok", type="output_text", annotations=[])],
                role="assistant",
                status="completed",
                type="message",
            )
            return ModelResponse(output=[msg], usage=usage, response_id="resp_1")

        def stream_response(
            self,
            system_instructions: str | None,
            input: str | list[TResponseInputItem],
            model_settings: ModelSettings,
            tools: list[Tool],
            output_schema: AgentOutputSchemaBase | None,
            handoffs: list[Handoff],
            tracing: ModelTracing,
            *,
            previous_response_id: str | None,
            conversation_id: str | None,
            prompt: ResponsePromptParam | None,
        ) -> AsyncIterator[TResponseStreamEvent]:
            async def _stream() -> AsyncIterator[TResponseStreamEvent]:
                if False:
                    yield typing.cast(TResponseStreamEvent, {})
                return

            return _stream()

    model_name = "test/model-instance"
    agent = Agent(name="ModelInstanceAgent", instructions="Respond with 'ok'.", model=FakeModel(model_name))
    result = await agent.get_response("hi")

    assert typing.cast(_HasMainAgentModel, result)._main_agent_model == model_name

    usage_stats = extract_usage_from_run_result(result)
    assert usage_stats is not None

    pricing_data = {
        model_name: {
            "input_cost_per_token": 1.0,
            "cache_read_input_token_cost": 0.0,
            "output_cost_per_token": 1.0,
            "output_cost_per_reasoning_token": 0.0,
        }
    }
    with_cost = calculate_usage_with_cost(usage_stats, pricing_data=pricing_data, run_result=result)
    assert with_cost.total_cost == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_calculate_usage_with_cost_prefers_usage_tracking_model_name() -> None:
    """Regression: proxy aliases should keep pricing tied to the real upstream model."""

    class FakeOpenClawModel(Model):
        model = "openclaw:main"
        _agency_swarm_usage_model_name = "openai/gpt-5.4"

        async def get_response(
            self,
            system_instructions: str | None,
            input: str | list[TResponseInputItem],
            model_settings: ModelSettings,
            tools: list[Tool],
            output_schema: AgentOutputSchemaBase | None,
            handoffs: list[Handoff],
            tracing: ModelTracing,
            *,
            previous_response_id: str | None,
            conversation_id: str | None,
            prompt: ResponsePromptParam | None,
        ) -> ModelResponse:
            usage = Usage(
                requests=1,
                input_tokens=2,
                output_tokens=1,
                total_tokens=3,
                input_tokens_details=InputTokensDetails(cached_tokens=0),
                output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
            )
            msg = ResponseOutputMessage(
                id="msg_2",
                content=[ResponseOutputText(text="ok", type="output_text", annotations=[])],
                role="assistant",
                status="completed",
                type="message",
            )
            return ModelResponse(output=[msg], usage=usage, response_id="resp_2")

        def stream_response(
            self,
            system_instructions: str | None,
            input: str | list[TResponseInputItem],
            model_settings: ModelSettings,
            tools: list[Tool],
            output_schema: AgentOutputSchemaBase | None,
            handoffs: list[Handoff],
            tracing: ModelTracing,
            *,
            previous_response_id: str | None,
            conversation_id: str | None,
            prompt: ResponsePromptParam | None,
        ) -> AsyncIterator[TResponseStreamEvent]:
            async def _stream() -> AsyncIterator[TResponseStreamEvent]:
                if False:
                    yield typing.cast(TResponseStreamEvent, {})
                return

            return _stream()

    agent = Agent(name="OpenClawProxyAgent", instructions="Respond with 'ok'.", model=FakeOpenClawModel())
    result = await agent.get_response("hi")

    assert typing.cast(_HasMainAgentModel, result)._main_agent_model == "openai/gpt-5.4"

    usage_stats = extract_usage_from_run_result(result)
    assert usage_stats is not None

    pricing_data = {
        "gpt-5.4": {
            "input_cost_per_token": 1.0,
            "cache_read_input_token_cost": 0.0,
            "output_cost_per_token": 2.0,
            "output_cost_per_reasoning_token": 0.0,
        }
    }
    with_cost = calculate_usage_with_cost(usage_stats, pricing_data=pricing_data, run_result=result)
    assert with_cost.total_cost == pytest.approx(4.0)


def test_load_pricing_data_is_single_load_under_concurrency(tmp_path, monkeypatch) -> None:
    """Regression: cache lock must prevent concurrent duplicate JSON parses."""
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text('{"test/model": {"input_cost_per_token": 1}}', encoding="utf-8")
    monkeypatch.setattr(usage_tracking, "PRICING_FILE_PATH", pricing_file)
    monkeypatch.setattr(usage_tracking, "_PRICING_DATA_CACHE", None)

    original_json_load = usage_tracking.json.load
    call_count = 0
    first_load_started = threading.Event()
    allow_return = threading.Event()

    def blocking_load(fp: typing.Any) -> typing.Any:
        nonlocal call_count
        call_count += 1
        first_load_started.set()
        assert allow_return.wait(timeout=1.0), "Test timed out waiting to release json.load"
        return original_json_load(fp)

    monkeypatch.setattr(usage_tracking.json, "load", blocking_load)

    results: list[usage_tracking.PricingData] = []
    results_lock = threading.Lock()

    def worker() -> None:
        data = usage_tracking.load_pricing_data()
        with results_lock:
            results.append(data)

    first_thread = threading.Thread(target=worker, daemon=True)
    first_thread.start()
    assert first_load_started.wait(timeout=1.0)

    second_thread = threading.Thread(target=worker, daemon=True)
    second_thread.start()

    try:
        time.sleep(0.05)
    finally:
        allow_return.set()
        first_thread.join(timeout=1.0)
        second_thread.join(timeout=1.0)

    assert call_count == 1, f"Expected a single JSON load under lock, got {call_count}"
    assert results
    assert all("test/model" in data for data in results)


def test_load_pricing_data_does_not_cache_invalid_json(tmp_path, monkeypatch) -> None:
    """Regression: invalid JSON must not poison the in-process cache."""
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text("{", encoding="utf-8")
    monkeypatch.setattr(usage_tracking, "PRICING_FILE_PATH", pricing_file)
    monkeypatch.setattr(usage_tracking, "_PRICING_DATA_CACHE", None)

    first = usage_tracking.load_pricing_data()
    assert first == {}

    pricing_file.write_text('{"test/model": {"input_cost_per_token": 1}}', encoding="utf-8")
    second = usage_tracking.load_pricing_data()
    assert "test/model" in second


def test_load_pricing_data_returns_empty_when_file_missing(tmp_path, monkeypatch) -> None:
    missing_file = tmp_path / "missing_pricing.json"
    monkeypatch.setattr(usage_tracking, "PRICING_FILE_PATH", missing_file)
    monkeypatch.setattr(usage_tracking, "_PRICING_DATA_CACHE", None)

    assert usage_tracking.load_pricing_data() == {}


def test_load_pricing_data_handles_non_dict_payload_and_coerces_bool_prices(tmp_path, monkeypatch) -> None:
    pricing_file = tmp_path / "pricing.json"
    monkeypatch.setattr(usage_tracking, "PRICING_FILE_PATH", pricing_file)

    pricing_file.write_text('["unexpected"]', encoding="utf-8")
    monkeypatch.setattr(usage_tracking, "_PRICING_DATA_CACHE", None)
    assert usage_tracking.load_pricing_data() == {}

    pricing_file.write_text(
        '{"test/model":{"input_cost_per_token":true,"output_cost_per_token":2,"cache_read_input_token_cost":false}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(usage_tracking, "_PRICING_DATA_CACHE", None)
    loaded = usage_tracking.load_pricing_data()
    assert loaded["test/model"]["input_cost_per_token"] == 0.0
    assert loaded["test/model"]["cache_read_input_token_cost"] == 0.0
    assert loaded["test/model"]["output_cost_per_token"] == 2.0


def test_get_model_pricing_resolves_provider_and_version_fallbacks() -> None:
    pricing_data = {
        "azure/gpt-4o": {"input_cost_per_token": 2.0},
        "gpt-4o": {"input_cost_per_token": 1.0},
    }

    assert get_model_pricing("azure/gpt-4o", pricing_data) == pricing_data["azure/gpt-4o"]
    assert get_model_pricing("openai/gpt-4o", pricing_data) == pricing_data["gpt-4o"]
    assert get_model_pricing("gpt-4o-2024-05-13", pricing_data) == pricing_data["gpt-4o"]
    assert get_model_pricing("gpt-4o-mini", pricing_data) == pricing_data["gpt-4o"]
    assert get_model_pricing("missing-model", pricing_data) is None


def test_calculate_openai_cost_handles_cached_and_reasoning_tokens() -> None:
    pricing_data = {
        "test/model": {
            "input_cost_per_token": 1.0,
            "output_cost_per_token": 2.0,
            "cache_read_input_token_cost": 0.5,
            "output_cost_per_reasoning_token": 3.0,
        }
    }

    cost = calculate_openai_cost(
        model_name="test/model",
        input_tokens=10,
        output_tokens=2,
        cached_tokens=4,
        reasoning_tokens=1,
        pricing_data=pricing_data,
    )
    assert cost == pytest.approx(15.0)
    assert calculate_openai_cost("missing", 1, 1, pricing_data=pricing_data) == 0.0


def test_bundled_pricing_supports_gpt_5_4_and_mini_defaults() -> None:
    pricing_data = load_pricing_data()

    assert get_model_pricing("gpt-5.4", pricing_data) is not None
    assert get_model_pricing("openai/gpt-5.4", pricing_data) == pricing_data["gpt-5.4"]
    assert calculate_openai_cost("gpt-5.4", 1000, 1000, pricing_data=pricing_data) > 0.0
    assert calculate_openai_cost("openai/gpt-5.4", 1000, 1000, pricing_data=pricing_data) > 0.0
    assert get_model_pricing("gpt-5.4-mini", pricing_data) is not None
    assert get_model_pricing("openai/gpt-5.4-mini", pricing_data) == pricing_data["gpt-5.4-mini"]
    assert calculate_openai_cost("gpt-5.4-mini", 1000, 1000, pricing_data=pricing_data) > 0.0
    assert calculate_openai_cost("openai/gpt-5.4-mini", 1000, 1000, pricing_data=pricing_data) > 0.0


def test_extract_usage_from_run_result_skips_malformed_subagent_entries() -> None:
    usage = Usage(
        requests=1,
        input_tokens=5,
        output_tokens=3,
        total_tokens=8,
        input_tokens_details=InputTokensDetails(cached_tokens=1),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )
    run_result = _make_run_result(usage=usage)
    typing.cast(_HasSubAgentResponsesWithModel, run_result)._sub_agent_responses_with_model = [
        ("broken", typing.cast(ModelResponse, object())),
    ]

    stats = extract_usage_from_run_result(run_result)
    assert stats is not None
    assert stats.request_count == 1
    assert stats.total_tokens == 8


def test_extract_usage_from_run_result_returns_none_for_unusable_context_wrapper() -> None:
    run_result = SimpleNamespace(context_wrapper=object())
    assert extract_usage_from_run_result(typing.cast(RunResult, run_result)) is None


def test_calculate_usage_with_cost_falls_back_to_full_litellm_path() -> None:
    usage_stats = UsageStats(
        request_count=1,
        cached_tokens=0,
        input_tokens=2,
        output_tokens=3,
        total_tokens=5,
        total_cost=0.0,
        reasoning_tokens=None,
        audio_tokens=None,
    )
    pricing_data = {
        "litellm/anthropic/claude-sonnet-4": {
            "input_cost_per_token": 1.0,
            "output_cost_per_token": 2.0,
            "cache_read_input_token_cost": 0.0,
            "output_cost_per_reasoning_token": 0.0,
        }
    }

    result = calculate_usage_with_cost(
        usage_stats,
        model_name="litellm/anthropic/claude-sonnet-4",
        pricing_data=pricing_data,
    )
    assert result.total_cost == pytest.approx(8.0)


def test_calculate_usage_with_cost_handles_run_result_without_model_name() -> None:
    usage = Usage(
        requests=1,
        input_tokens=2,
        output_tokens=1,
        total_tokens=3,
        input_tokens_details=InputTokensDetails(cached_tokens=0),
        output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
    )
    response = ModelResponse(output=[], usage=usage, response_id=None)
    run_result = SimpleNamespace(raw_responses=[response], _sub_agent_responses_with_model=[])

    usage_stats = UsageStats(
        request_count=1,
        cached_tokens=0,
        input_tokens=2,
        output_tokens=1,
        total_tokens=3,
        total_cost=123.0,
        reasoning_tokens=None,
        audio_tokens=None,
    )
    with_cost = calculate_usage_with_cost(usage_stats, run_result=typing.cast(RunResult, run_result))
    assert with_cost.total_cost == 0.0


def test_format_usage_for_display_includes_optional_fields() -> None:
    usage_stats = UsageStats(
        request_count=2,
        cached_tokens=3,
        input_tokens=10,
        output_tokens=7,
        total_tokens=17,
        total_cost=1.234567,
        reasoning_tokens=2,
        audio_tokens=1,
    )

    formatted = format_usage_for_display(usage_stats, model_name="gpt-5.4-mini")
    assert "Model: gpt-5.4-mini" in formatted
    assert "Requests: 2" in formatted
    assert "Cached: 3" in formatted
    assert "Reasoning: 2" in formatted
    assert "Audio: 1" in formatted
    assert "Cost: $1.234567" in formatted
