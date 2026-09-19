"""End-to-end coverage for the classic tool-result history bug.

A turn that produces a function call (or a ``send_message`` delegation) must
persist the call and its output so that the *next* turn resends that history to
the model as proper ``function_call``/``function_call_output`` items — not as
rewritten assistant text, and not dropped entirely.
"""

from __future__ import annotations

import copy
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from agents import Tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ModelSettings
from agents.models.interface import ModelTracing
from openai.types.responses import ResponseFunctionToolCall
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, Agent, function_tool
from tests.deterministic_model import DeterministicModel, _stream_output_item_events


class _HistoryRecordingModel(DeterministicModel):
    """DeterministicModel that records every input it receives."""

    def __init__(self) -> None:
        super().__init__()
        self.inputs: list[list[TResponseInputItem]] = []

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
        self.inputs.append(copy.deepcopy(input) if isinstance(input, list) else [])
        return await super().get_response(
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )

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
        self.inputs.append(copy.deepcopy(input) if isinstance(input, list) else [])
        return super().stream_response(
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )


class _StreamingToolCallModel(_HistoryRecordingModel):
    """Emits one echo_tool call on the first streamed turn, then falls back to text."""

    def __init__(self) -> None:
        super().__init__()
        self.emitted_tool_call = False

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
        self.inputs.append(copy.deepcopy(input) if isinstance(input, list) else [])
        if not self.emitted_tool_call and any(tool.name == "echo_tool" for tool in tools):
            self.emitted_tool_call = True
            tool_call = ResponseFunctionToolCall(
                arguments=json.dumps({"message": "stream hello"}),
                call_id="call_stream_echo",
                name="echo_tool",
                type="function_call",
                id="fc_stream_echo",
                status="completed",
            )
            return _stream_output_item_events([tool_call], self.model)
        return DeterministicModel.stream_response(
            self,
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            tracing,
            previous_response_id=previous_response_id,
            conversation_id=conversation_id,
            prompt=prompt,
        )


@function_tool
async def echo_tool(message: str) -> str:
    """Echo a message back to the caller."""
    return f"Echo: {message}"


def _function_calls(input_items: list[TResponseInputItem]) -> list[dict[str, Any]]:
    return [item for item in input_items if isinstance(item, dict) and item.get("type") == "function_call"]


def _function_outputs(input_items: list[TResponseInputItem]) -> list[dict[str, Any]]:
    return [item for item in input_items if isinstance(item, dict) and item.get("type") == "function_call_output"]


def _assert_tool_history_resent(
    second_turn_input: list[TResponseInputItem],
    *,
    tool_name: str,
    expected_output_fragment: str,
) -> None:
    calls = _function_calls(second_turn_input)
    outputs = _function_outputs(second_turn_input)

    tool_calls = [call for call in calls if call.get("name") == tool_name]
    assert tool_calls, f"second-turn input dropped the {tool_name} function_call: {second_turn_input}"

    call_ids = {call.get("call_id") for call in tool_calls}
    matching_outputs = [output for output in outputs if output.get("call_id") in call_ids]
    assert matching_outputs, (
        f"second-turn input has the {tool_name} call but no matching function_call_output: {second_turn_input}"
    )
    assert any(expected_output_fragment in str(output.get("output", "")) for output in matching_outputs), (
        f"tool output for {tool_name} was not resent verbatim: {matching_outputs}"
    )

    # The tool result must stay a function_call_output item — not rewritten into
    # assistant message text, which is the failure mode this regression covers.
    assert not any(
        isinstance(item, dict)
        and item.get("role") == "assistant"
        and "Tool output for call" in str(item.get("content", ""))
        for item in second_turn_input
    )


@pytest.mark.asyncio
async def test_function_call_result_is_resent_to_model_on_next_turn() -> None:
    model = _HistoryRecordingModel()
    agent = Agent(
        name="EchoAgent",
        instructions="You echo messages with the echo_tool.",
        model=model,
        tools=[echo_tool],
    )
    agency = Agency(agent)

    await agency.get_response("echo 'hello world'", recipient_agent=agent)
    await agency.get_response("what did the tool say?", recipient_agent=agent)

    assert len(model.inputs) >= 3, f"expected tool call turn + next turn, got {len(model.inputs)} calls"
    _assert_tool_history_resent(
        model.inputs[-1],
        tool_name="echo_tool",
        expected_output_fragment="Echo: hello world",
    )


@pytest.mark.asyncio
async def test_function_call_result_is_resent_to_model_on_next_turn_streaming() -> None:
    model = _StreamingToolCallModel()
    agent = Agent(
        name="EchoAgent",
        instructions="You echo messages with the echo_tool.",
        model=model,
        tools=[echo_tool],
    )
    agency = Agency(agent)

    async for _ in agency.get_response_stream("echo 'stream hello'", recipient_agent=agent):
        pass
    async for _ in agency.get_response_stream("what did the tool say?", recipient_agent=agent):
        pass

    assert len(model.inputs) >= 3, f"expected tool call turn + next turn, got {len(model.inputs)} calls"
    _assert_tool_history_resent(
        model.inputs[-1],
        tool_name="echo_tool",
        expected_output_fragment="Echo: stream hello",
    )


@pytest.mark.asyncio
async def test_delegation_result_is_resent_to_model_on_next_turn() -> None:
    coordinator_model = _HistoryRecordingModel()
    worker = Agent(
        name="Worker",
        instructions="You complete delegated tasks.",
        model=DeterministicModel(),
    )
    coordinator = Agent(
        name="Coordinator",
        instructions="You delegate tasks to Worker with the send_message tool.",
        model=coordinator_model,
    )
    agency = Agency(coordinator, communication_flows=[coordinator > worker])

    await agency.get_response("tell Worker to handle task-onboarding", recipient_agent=coordinator)
    await agency.get_response("what did Worker report?", recipient_agent=coordinator)

    assert len(coordinator_model.inputs) >= 3, (
        f"expected delegation turn + next turn, got {len(coordinator_model.inputs)} calls"
    )
    _assert_tool_history_resent(
        coordinator_model.inputs[-1],
        tool_name="send_message",
        expected_output_fragment="TASK_COMPLETED",
    )
