"""Chained handoffs within a single run must keep runtime handoffs available.

Regression coverage for A -> B -> C handoff chains executed in one turn: the
SDK run loop switches to the recipient agent without re-entering
``setup_execution``, so runtime-state handoffs must be attached to every
agency agent before ``Runner.run`` starts.
"""

from collections.abc import AsyncIterator

import pytest
from agents import Usage
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff as SDKHandoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.model_settings import ModelSettings
from agents.models.interface import Model, ModelTracing
from agents.tool import Tool
from openai.types.responses import (
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)
from openai.types.responses.response_prompt_param import ResponsePromptParam
from openai.types.responses.response_usage import InputTokensDetails, OutputTokensDetails

from agency_swarm import Agency, Agent
from agency_swarm.tools import Handoff


class ScriptedHandoffModel(Model):
    """Offline model that hands off when the target tool is offered.

    Records the handoff tool names offered on every model call so tests can
    assert which handoffs the run loop actually exposed to each agent.
    """

    def __init__(self, target_handoff: str | None, final_text: str) -> None:
        self.model = "scripted-fake-model"
        self.target_handoff = target_handoff
        self.final_text = final_text
        self.offered_handoffs: list[list[str]] = []

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
        offered = [h.tool_name for h in handoffs]
        self.offered_handoffs.append(offered)

        usage = Usage(
            requests=1,
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
            input_tokens_details=InputTokensDetails(cached_tokens=0),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=0),
        )

        if self.target_handoff and self.target_handoff in offered:
            recipient = self.target_handoff.removeprefix("transfer_to_")
            call = ResponseFunctionToolCall(
                id=f"fc_{recipient}",
                call_id=f"call_{recipient}",
                name=self.target_handoff,
                arguments=f'{{"recipient_agent": "{recipient}"}}',
                type="function_call",
            )
            return ModelResponse(output=[call], usage=usage, response_id=f"resp_{recipient}")

        msg = ResponseOutputMessage(
            id="msg_final",
            content=[ResponseOutputText(text=self.final_text, type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        )
        return ModelResponse(output=[msg], usage=usage, response_id="resp_final")

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
        raise NotImplementedError("streaming is not exercised in this test")


def _build_chained_agency() -> tuple[Agency, ScriptedHandoffModel, ScriptedHandoffModel, ScriptedHandoffModel]:
    model_a = ScriptedHandoffModel("transfer_to_AgentB", "A done")
    model_b = ScriptedHandoffModel("transfer_to_AgentC", "B stopped: no handoff tools")
    model_c = ScriptedHandoffModel(None, "C done")

    agent_a = Agent(name="AgentA", instructions="Hand off to AgentB.", model=model_a)
    agent_b = Agent(name="AgentB", instructions="Hand off to AgentC.", model=model_b)
    agent_c = Agent(name="AgentC", instructions="Finish the task.", model=model_c)

    agency = Agency(
        agent_a,
        communication_flows=[
            (agent_a > agent_b, Handoff),
            (agent_b > agent_c, Handoff),
        ],
    )
    return agency, model_a, model_b, model_c


@pytest.mark.asyncio
async def test_same_turn_chained_handoff_reaches_final_agent() -> None:
    """A -> B -> C chained handoffs in one turn must reach AgentC."""
    agency, model_a, model_b, model_c = _build_chained_agency()

    result = await agency.get_response("Please chain to AgentC.")

    assert model_a.offered_handoffs[0] == ["transfer_to_AgentB"]
    assert model_b.offered_handoffs, "AgentB was never reached via handoff"
    assert model_b.offered_handoffs[0] == ["transfer_to_AgentC"], (
        "AgentB lost its runtime handoffs after the mid-run agent switch"
    )
    assert model_c.offered_handoffs, "AgentC was never reached via chained handoff"
    assert result.final_output == "C done"


@pytest.mark.asyncio
async def test_runtime_handoffs_are_restored_after_run() -> None:
    """Runtime handoffs must not leak onto agents once the run finishes."""
    agency, _, _, _ = _build_chained_agency()

    await agency.get_response("Please chain to AgentC.")

    for name in ("AgentA", "AgentB", "AgentC"):
        assert agency.agents[name].handoffs == [], f"{name} kept runtime handoffs after cleanup"
