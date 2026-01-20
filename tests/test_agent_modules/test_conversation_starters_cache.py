from agency_swarm import Agent, GuardrailFunctionOutput, RunContextWrapper, input_guardrail, output_guardrail
from agency_swarm.agent.conversation_starters_cache import compute_starter_cache_fingerprint


@input_guardrail(name="RequireSupportPrefix")
def require_support_prefix(
    context: RunContextWrapper, agent: Agent, input_message: str | list[str]
) -> GuardrailFunctionOutput:
    return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)


@output_guardrail(name="BlockEmails")
def block_emails(context: RunContextWrapper, agent: Agent, response_text: str) -> GuardrailFunctionOutput:
    return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)


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
