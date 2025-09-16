import pytest

from agency_swarm import (
    Agency,
    Agent,
    GuardrailFunctionOutput,
    ModelSettings,
    RunContextWrapper,
    input_guardrail,
    output_guardrail,
)


@input_guardrail(name="RequireSupportPrefix")
async def require_support_prefix(
    context: RunContextWrapper, agent: Agent, input_message: str | list[str]
) -> GuardrailFunctionOutput:
    if isinstance(input_message, str):
        bad = not input_message.startswith("Support:")
    else:
        bad = any(isinstance(s, str) and not s.startswith("Support:") for s in input_message)
    return GuardrailFunctionOutput(
        output_info=("Please, prefix your request with 'Support:' describing what you need." if bad else ""),
        tripwire_triggered=bad,
    )


@output_guardrail(name="ForbidEmailOutput")
async def forbid_email_output(context: RunContextWrapper, agent: Agent, response_text: str) -> GuardrailFunctionOutput:
    text = (response_text or "").strip()
    if "@" in text:
        return GuardrailFunctionOutput(
            output_info=("Email addresses are not allowed in responses."),
            tripwire_triggered=True,
        )
    return GuardrailFunctionOutput(output_info="", tripwire_triggered=False)


def _make_agency_for_input_guardrail() -> Agency:
    agent = Agent(
        name="InputGuardrailAgent",
        instructions="You are a helpful assistant.",
        model="gpt-4o",
        input_guardrails=[require_support_prefix],
        model_settings=ModelSettings(temperature=0.0),
        throw_input_guardrail_error=False,
    )
    return Agency(agent)


def _make_agency_for_output_guardrail() -> Agency:
    agent = Agent(
        name="OutputGuardrailAgent",
        # Instruct model to output an email to trip the guardrail on first attempt
        instructions=("You are a helpful assistant. Respond with exactly 'foo@example.com' and nothing else."),
        model="gpt-4o",
        output_guardrails=[forbid_email_output],
        model_settings=ModelSettings(temperature=0.0),
        validation_attempts=1,  # allow one retry without email
    )
    return Agency(agent)


@pytest.mark.asyncio
async def test_input_guardrail_guidance_and_persistence():
    agency = _make_agency_for_input_guardrail()
    resp = await agency.get_response(message="Hello there")

    # Should return guidance as final_output without calling the model
    assert isinstance(resp.final_output, str)
    assert "prefix your request with 'Support:'" in resp.final_output

    # System guidance should be persisted in thread history exactly once
    all_msgs = agency.thread_manager.get_all_messages()
    system_msgs = [m for m in all_msgs if m.get("role") == "system"]
    assert len(system_msgs) == 1
    assert "prefix your request with 'Support:'" in system_msgs[0].get("content", "")


@pytest.mark.asyncio
async def test_output_guardrail_logs_guidance():
    agency = _make_agency_for_output_guardrail()
    await agency.get_response(message="Hi")

    # History should contain a system guidance message from the guardrail
    all_msgs = agency.thread_manager.get_all_messages()
    system_msgs = [m for m in all_msgs if m.get("role") == "system"]
    assert any("Email addresses are not allowed" in (m.get("content", "")) for m in system_msgs)


@pytest.mark.asyncio
async def test_input_guardrail_multiple_agent_inits_no_double_wrap():
    # Initialize Agents multiple times BEFORE sending any query to simulate
    # environments that construct agents repeatedly (shared guardrail instances).

    # Now create the agent/agency we actually use for the request
    def create_agency():
        final_agent = Agent(
            name="FinalInputGuardrailAgent",
            instructions="You are a helpful assistant.",
            model="gpt-4o",
            input_guardrails=[require_support_prefix],
            model_settings=ModelSettings(temperature=0.0),
            throw_input_guardrail_error=False,
        )
        agency = Agency(final_agent)
        return agency

    for _ in range(3):
        agency = create_agency()

    resp = await agency.get_response(
        message=[{"role": "user", "content": "Hi"}, {"role": "user", "content": "How are you?"}]
    )

    # Guidance must be returned
    assert isinstance(resp.final_output, str)
    assert "prefix your request with 'Support:'" in resp.final_output

    # Ensure only a single system guidance message is persisted (no stacked wrappers)
    all_msgs = agency.thread_manager.get_all_messages()
    system_msgs = [m for m in all_msgs if m.get("role") == "system"]
    assert len(system_msgs) == 1
    assert "prefix your request with 'Support:'" in system_msgs[0].get("content", "")
