from collections.abc import AsyncIterator

import pytest
from agents import Tool
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff as SDKHandoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ModelSettings
from agents.models.interface import Model, ModelTracing
from openai.types.responses.response_prompt_param import ResponsePromptParam

from agency_swarm import Agency, Agent
from tests.deterministic_model import _build_message_response, _stream_text_events


class SystemInstructionsEchoModel(Model):
    def __init__(self, model: str = "test-system-instructions") -> None:
        self.model = model

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[SDKHandoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        text = system_instructions or ""
        return _build_message_response(text, self.model)

    def stream_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[SDKHandoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> AsyncIterator[TResponseStreamEvent]:
        text = system_instructions or ""
        return _stream_text_events(text, self.model)


@pytest.mark.asyncio
async def test_agent_get_response_applies_additional_instructions_and_restores_original() -> None:
    original_instructions = "Base agent instructions."
    additional_instructions = "Additional run instructions."
    agent = Agent(
        name="TestAgent",
        instructions=original_instructions,
        model=SystemInstructionsEchoModel(),
    )

    result = await agent.get_response("hello", additional_instructions=additional_instructions)

    assert isinstance(result.final_output, str)
    assert result.final_output == f"{original_instructions}\n\n{additional_instructions}"
    assert agent.instructions == original_instructions


@pytest.mark.asyncio
async def test_agent_get_response_stream_applies_additional_instructions_and_restores_original() -> None:
    original_instructions = "Base agent instructions."
    additional_instructions = "Streaming run instructions."
    agent = Agent(
        name="TestAgent",
        instructions=original_instructions,
        model=SystemInstructionsEchoModel(),
    )

    stream = agent.get_response_stream("hello", additional_instructions=additional_instructions)
    async for _event in stream:
        pass

    assert stream.final_output == f"{original_instructions}\n\n{additional_instructions}"
    assert agent.instructions == original_instructions


@pytest.mark.asyncio
async def test_agency_shared_instructions_precede_base_and_additional() -> None:
    shared_instructions = "Shared agency instructions."
    base_instructions = "Base agent instructions."
    additional_instructions = "Additional run instructions."
    agent = Agent(
        name="TestAgent",
        instructions=base_instructions,
        model=SystemInstructionsEchoModel(),
    )
    agency = Agency(agent, shared_instructions=shared_instructions)

    result = await agency.get_response("hello", additional_instructions=additional_instructions)

    assert isinstance(result.final_output, str)
    assert result.final_output == (f"{shared_instructions}\n\n{base_instructions}\n\n---\n\n{additional_instructions}")
    assert agent.instructions == base_instructions


@pytest.mark.asyncio
async def test_agency_uses_latest_shared_instructions_between_runs() -> None:
    base_instructions = "Base agent instructions."
    additional_instructions = "Additional run instructions."
    initial_shared_instructions = "Initial shared instructions."
    updated_shared_instructions = "Updated shared instructions."
    agent = Agent(
        name="TestAgent",
        instructions=base_instructions,
        model=SystemInstructionsEchoModel(),
    )
    agency = Agency(agent, shared_instructions=initial_shared_instructions)

    first = await agency.get_response("hello", additional_instructions=additional_instructions)
    assert isinstance(first.final_output, str)
    assert first.final_output == (
        f"{initial_shared_instructions}\n\n{base_instructions}\n\n---\n\n{additional_instructions}"
    )

    agency.shared_instructions = updated_shared_instructions
    second = await agency.get_response("hello", additional_instructions=additional_instructions)

    assert isinstance(second.final_output, str)
    assert second.final_output == (
        f"{updated_shared_instructions}\n\n{base_instructions}\n\n---\n\n{additional_instructions}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("additional_instructions", ["", None])
async def test_empty_or_none_additional_instructions_do_not_add_separator(
    additional_instructions: str | None,
) -> None:
    original_instructions = "Base agent instructions."
    agent = Agent(
        name="TestAgent",
        instructions=original_instructions,
        model=SystemInstructionsEchoModel(),
    )

    result = await agent.get_response("hello", additional_instructions=additional_instructions)

    assert isinstance(result.final_output, str)
    assert result.final_output == original_instructions
    assert "---" not in result.final_output
    assert agent.instructions == original_instructions


@pytest.mark.asyncio
async def test_additional_instructions_with_none_base_instructions() -> None:
    additional_instructions = "Additional run instructions only."
    agent = Agent(
        name="NoBaseInstructionsAgent",
        instructions=None,
        model=SystemInstructionsEchoModel(),
    )

    result = await agent.get_response("hello", additional_instructions=additional_instructions)

    assert isinstance(result.final_output, str)
    assert result.final_output == additional_instructions
    assert agent.instructions is None
