from typing import Any

import pytest
from agents import ModelSettings
from agents.items import HandoffOutputItem
from agents.lifecycle import RunHooksBase

from agency_swarm import Agency, Agent, Handoff
from tests.deterministic_model import DeterministicModel


class RecordingDeterministicModel(DeterministicModel):
    def __init__(self, model: str, default_response: str) -> None:
        super().__init__(model=model, default_response=default_response)
        self.seen_model_settings: list[ModelSettings] = []

    async def get_response(self, *args: Any, **kwargs: Any) -> Any:
        model_settings = kwargs["model_settings"] if "model_settings" in kwargs else args[2]
        self.seen_model_settings.append(model_settings)
        return await super().get_response(*args, **kwargs)


class RecordingHooks(RunHooksBase[Any, Agent]):
    def __init__(self) -> None:
        self.agent_starts: list[Agent] = []
        self.llm_starts: list[Agent] = []

    async def on_agent_start(self, context: Any, agent: Agent) -> None:
        self.agent_starts.append(agent)

    async def on_llm_start(
        self,
        context: Any,
        agent: Agent,
        system_prompt: str | None,
        input_items: list[Any],
    ) -> None:
        self.llm_starts.append(agent)


@pytest.mark.asyncio
async def test_result_last_agent_routes_follow_up_to_registered_agent() -> None:
    """RunResult.last_agent should remain usable as a public Agency recipient."""
    agent = Agent(
        name="SupportAgent",
        instructions="Answer directly.",
        model=DeterministicModel(default_response="handled"),
        model_settings=ModelSettings(max_tokens=16),
    )
    agency = Agency(agent)

    result = await agency.get_response("Start with SupportAgent")
    follow_up = await agency.get_response("Continue with SupportAgent", recipient_agent=result.last_agent)

    assert result.last_agent is agent
    assert follow_up.last_agent is agent
    assert follow_up.final_output == "handled"


@pytest.mark.asyncio
async def test_result_new_items_use_registered_agent() -> None:
    """Public RunItems should expose the registered Agent, not runner-private copies."""
    agent = Agent(
        name="SupportAgent",
        instructions="Answer directly.",
        model=DeterministicModel(default_response="handled"),
        model_settings=ModelSettings(max_tokens=16),
    )
    agency = Agency(agent)

    result = await agency.get_response("Start with SupportAgent")

    assert result.new_items
    assert result.last_agent is agent
    for item in result.new_items:
        assert item.agent is agent


@pytest.mark.asyncio
async def test_callbacks_and_callable_instructions_receive_registered_agent() -> None:
    """Runner callbacks and callable instructions should see the public registered Agent."""
    instruction_agents: list[Agent] = []

    async def dynamic_instructions(context: Any, agent_instance: Agent) -> str:
        instruction_agents.append(agent_instance)
        return "Answer directly."

    hooks = RecordingHooks()
    agent = Agent(
        name="SupportAgent",
        instructions="Answer directly.",
        model=DeterministicModel(default_response="handled"),
        model_settings=ModelSettings(max_tokens=16),
    )
    agent.instructions = dynamic_instructions

    result = await agent.get_response("Start with SupportAgent", hooks_override=hooks)

    assert result.last_agent is agent
    assert instruction_agents == [agent]
    assert hooks.agent_starts == [agent]
    assert hooks.llm_starts == [agent]


@pytest.mark.asyncio
async def test_handoff_recipient_uses_runner_compatible_settings_without_mutating_public_agent() -> None:
    """Handoff targets should run through normalized per-run public agents."""
    recipient_model = RecordingDeterministicModel(model="gpt-5.4-mini", default_response="recipient handled")
    triage_agent = Agent(
        name="TriageAgent",
        instructions="Transfer to SupportAgent when asked.",
        model=DeterministicModel(model="gpt-4.1-mini"),
        model_settings=ModelSettings(max_tokens=16),
    )
    support_agent = Agent(
        name="SupportAgent",
        instructions="Answer after transfer.",
        model=recipient_model,
        model_settings=ModelSettings(temperature=0.3, max_tokens=16),
    )
    agency = Agency(
        triage_agent,
        communication_flows=[(triage_agent > support_agent, Handoff)],
    )
    runtime_handoff = agency.get_agent_runtime_state("TriageAgent").handoffs[0]
    recipient_ref = getattr(runtime_handoff, "_agent_ref", None)

    with pytest.warns(UserWarning, match="does not support temperature"):
        result = await agency.get_response("Transfer this to SupportAgent.")

    assert recipient_model.seen_model_settings
    assert recipient_model.seen_model_settings[0].temperature is None
    assert recipient_model.seen_model_settings[0].max_tokens == 16
    assert support_agent.model_settings.temperature == 0.3
    assert support_agent.model_settings.max_tokens == 16
    assert result.last_agent is support_agent
    assert {id(item.agent) for item in result.new_items} == {id(triage_agent), id(support_agent)}
    handoff_output_items = [item for item in result.new_items if isinstance(item, HandoffOutputItem)]
    assert handoff_output_items
    assert handoff_output_items[0].source_agent is triage_agent
    assert handoff_output_items[0].target_agent is support_agent
    assert recipient_ref is not None
    assert recipient_ref() is support_agent
