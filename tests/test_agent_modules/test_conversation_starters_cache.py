from agents.items import HandoffOutputItem

from agency_swarm import Agent, GuardrailFunctionOutput, RunContextWrapper, input_guardrail, output_guardrail
from agency_swarm.agent.context_types import AgentRuntimeState
from agency_swarm.agent.conversation_starters_cache import (
    build_run_items_from_cached,
    compute_starter_cache_fingerprint,
    is_simple_text_message,
)
from agency_swarm.tools.send_message import Handoff


@input_guardrail(name="RequireSupportPrefix")
def require_support_prefix(
    context: RunContextWrapper, agent: Agent, input_message: str | list[str]
) -> GuardrailFunctionOutput:
    return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)


@output_guardrail(name="BlockEmails")
def block_emails(context: RunContextWrapper, agent: Agent, response_text: str) -> GuardrailFunctionOutput:
    return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)


def test_is_simple_text_message_requires_single_user_item() -> None:
    items = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello there."},
    ]

    assert is_simple_text_message(items) is False


def test_is_simple_text_message_rejects_multiple_user_items() -> None:
    items = [
        {"role": "user", "content": "Hello."},
        {"role": "user", "content": "Follow-up."},
    ]

    assert is_simple_text_message(items) is False


def test_starter_cache_fingerprint_includes_guardrails() -> None:
    agent_with_guardrails = Agent(
        name="GuardrailAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
        input_guardrails=[require_support_prefix],
        output_guardrails=[block_emails],
    )
    agent_without_guardrails = Agent(
        name="BaselineAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
        input_guardrails=[],
        output_guardrails=[],
    )

    fingerprint_with = compute_starter_cache_fingerprint(agent_with_guardrails)
    fingerprint_without = compute_starter_cache_fingerprint(agent_without_guardrails)

    assert fingerprint_with != fingerprint_without


def test_starter_cache_fingerprint_includes_runtime_send_message_tools() -> None:
    sender = Agent(
        name="SenderAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    recipient = Agent(
        name="RecipientAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    runtime_state = AgentRuntimeState()

    fingerprint_before = compute_starter_cache_fingerprint(sender, runtime_state=runtime_state)
    sender.register_subagent(recipient, runtime_state=runtime_state)
    fingerprint_after = compute_starter_cache_fingerprint(sender, runtime_state=runtime_state)

    assert fingerprint_before != fingerprint_after


def test_starter_cache_fingerprint_includes_runtime_handoffs() -> None:
    sender = Agent(
        name="HandoffSender",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    recipient = Agent(
        name="HandoffRecipient",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    runtime_state = AgentRuntimeState()

    fingerprint_before = compute_starter_cache_fingerprint(sender, runtime_state=runtime_state)
    runtime_state.handoffs.append(Handoff().create_handoff(recipient))
    fingerprint_after = compute_starter_cache_fingerprint(sender, runtime_state=runtime_state)

    assert fingerprint_before != fingerprint_after


def test_cached_handoff_output_preserves_type() -> None:
    agent = Agent(
        name="CacheAgent",
        instructions="You are helpful.",
        model="gpt-5-mini",
    )
    items = [
        {
            "type": "handoff_output_item",
            "call_id": "call_handoff_1",
            "output": '{"assistant": "Worker"}',
        }
    ]

    run_items = build_run_items_from_cached(agent, items)

    assert len(run_items) == 1
    assert isinstance(run_items[0], HandoffOutputItem)
