import pytest

from agency_swarm import (
    Agency,
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
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


@pytest.fixture
def input_guardrail_agent() -> Agent:
    return Agent(
        name="InputGuardrailAgent",
        instructions="You are a helpful assistant.",
        model="gpt-4o",
        input_guardrails=[require_support_prefix],
        model_settings=ModelSettings(temperature=0.0),
        throw_input_guardrail_error=False,
    )


@pytest.fixture
def input_guardrail_agency(input_guardrail_agent: Agent) -> Agency:
    return Agency(input_guardrail_agent)


@pytest.fixture
def input_guardrail_agency_factory():
    def factory() -> Agency:
        agent = Agent(
            name="InputGuardrailAgent",
            instructions="You are a helpful assistant.",
            model="gpt-4o",
            input_guardrails=[require_support_prefix],
            model_settings=ModelSettings(temperature=0.0),
            throw_input_guardrail_error=False,
        )
        return Agency(agent)

    return factory


@pytest.fixture
def output_guardrail_agent() -> Agent:
    return Agent(
        name="OutputGuardrailAgent",
        instructions=("You are a helpful assistant. Respond with exactly 'foo@example.com' and nothing else."),
        model="gpt-4o",
        output_guardrails=[forbid_email_output],
        model_settings=ModelSettings(temperature=0.0),
        validation_attempts=1,
    )


@pytest.fixture
def output_guardrail_agency(output_guardrail_agent: Agent) -> Agency:
    return Agency(output_guardrail_agent)


def test_input_guardrail_guidance_and_persistence(input_guardrail_agency: Agency):
    agency = input_guardrail_agency
    resp = agency.get_response_sync(message="Hello there")

    # Should return guidance as final_output without calling the model
    assert isinstance(resp.final_output, str)
    assert "prefix your request with 'Support:'" in resp.final_output

    # System guidance should be persisted in thread history exactly once
    all_msgs = agency.thread_manager.get_all_messages()
    system_msgs = [m for m in all_msgs if m.get("role") == "system"]
    assert len(system_msgs) == 1
    assert "prefix your request with 'Support:'" in system_msgs[-1].get("content", "")
    assert system_msgs[-1].get("message_origin") == "input_guardrail_message"


def test_input_guardrail_error(input_guardrail_agency: Agency):
    agency = input_guardrail_agency
    agency.agents["InputGuardrailAgent"].throw_input_guardrail_error = True

    # Should raise InputGuardrailTripwireTriggered exception when throw_input_guardrail_error is True
    with pytest.raises(InputGuardrailTripwireTriggered):
        agency.get_response_sync(message="Hello there")

    all_msgs = agency.thread_manager.get_all_messages()
    system_msgs = [m for m in all_msgs if m.get("role") == "system"]
    assert len(system_msgs) == 1
    assert "prefix your request with 'Support:'" in system_msgs[-1].get("content", "")
    assert system_msgs[-1].get("message_origin") == "input_guardrail_error"


def test_output_guardrail_logs_guidance(output_guardrail_agency: Agency):
    agency = output_guardrail_agency
    agency.get_response_sync(message="Hi")

    # History should contain a system guidance message from the guardrail
    all_msgs = agency.thread_manager.get_all_messages()
    system_msgs = [m for m in all_msgs if m.get("role") == "system"]
    assert any("Email addresses are not allowed" in (m.get("content", "")) for m in system_msgs)
    assert system_msgs[-1].get("message_origin") == "output_guardrail_error"


def test_input_guardrail_multiple_agent_inits_no_double_wrap(input_guardrail_agency_factory):
    # Initialize Agents multiple times BEFORE sending any query to simulate repeated setup
    for _ in range(3):
        agency = input_guardrail_agency_factory()

    resp = agency.get_response_sync(
        message=[{"role": "user", "content": "Hi"}, {"role": "user", "content": "How are you?"}]
    )

    # Guidance must be returned
    assert isinstance(resp.final_output, str)
    assert "prefix your request with 'Support:'" in resp.final_output

    # Ensure only a single system guidance message is persisted (no stacked wrappers)
    all_msgs = agency.thread_manager.get_all_messages()
    system_msgs = [m for m in all_msgs if m.get("role") == "system"]
    assert len(system_msgs) == 1
    assert "prefix your request with 'Support:'" in system_msgs[-1].get("content", "")
    assert system_msgs[-1].get("message_origin") == "input_guardrail_message"
