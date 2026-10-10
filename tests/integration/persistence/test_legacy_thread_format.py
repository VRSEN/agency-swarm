"""A thread saved by agency-swarm 1.11.0 must load through load_threads_callback and continue."""

import json
from pathlib import Path
from typing import Any

import pytest
from agents import Tool, function_tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem
from agents.model_settings import ModelSettings
from agents.models.interface import ModelTracing
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, Agent
from tests.deterministic_model import DeterministicModel

# Written by agency-swarm 1.11.0 save_threads_callback: a tool call turn, then a turn that holds a secret code.
THREAD_FILE = Path(__file__).parents[2] / "data" / "threads" / "thread_saved_by_1_11_0.json"


class RecordingModel(DeterministicModel):
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
        assert isinstance(input, list)
        self.inputs.append(list(input))
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


@function_tool
def echo_tool(message: str) -> str:
    """Echo the message."""
    return f"ECHO: {message}"


@pytest.mark.asyncio
async def test_thread_saved_by_1_11_0_loads_and_continues() -> None:
    legacy_thread: list[dict[str, Any]] = json.loads(THREAD_FILE.read_text())
    saved: list[list[dict[str, Any]]] = []
    model = RecordingModel()
    agency = Agency(
        Agent(name="Assistant", instructions="Help", model=model, tools=[echo_tool]),
        name="LegacyAgency",
        load_threads_callback=lambda: json.loads(THREAD_FILE.read_text()),
        save_threads_callback=lambda messages: saved.append(messages),
    )

    result = await agency.get_response("Do you remember it?")

    assert result.final_output == "REMEMBERED: ALPHA-7"
    model_input = model.inputs[-1]
    legacy_call_id = legacy_thread[1]["call_id"]
    assert any(item.get("type") == "function_call" and item.get("call_id") == legacy_call_id for item in model_input)
    assert any(
        item.get("type") == "function_call_output" and item.get("call_id") == legacy_call_id for item in model_input
    )

    stored = saved[-1]
    assert [item.get("timestamp") for item in stored[: len(legacy_thread)]] == [
        item["timestamp"] for item in legacy_thread
    ]
    new_items = stored[len(legacy_thread) :]
    assert [item.get("role") for item in new_items] == ["user", "assistant"]
    assert all(item.get("agent") == "Assistant" and item.get("history_protocol") == "responses" for item in new_items)
