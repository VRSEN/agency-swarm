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


def _evaluate_support_prefix_guardrail(input_message: str | list[str]) -> GuardrailFunctionOutput:
    if isinstance(input_message, str):
        bad = not input_message.startswith("Support:")
    else:
        bad = any(isinstance(s, str) and not s.startswith("Support:") for s in input_message)
    return GuardrailFunctionOutput(
        output_info=("Please, prefix your request with 'Support:' describing what you need." if bad else ""),
        tripwire_triggered=bad,
    )


@input_guardrail(name="RequireSupportPrefix")
async def require_support_prefix(
    context: RunContextWrapper, agent: Agent, input_message: str | list[str]
) -> GuardrailFunctionOutput:
    return _evaluate_support_prefix_guardrail(input_message)


@input_guardrail(name="RequireSupportPrefixAlias")
async def guardrail_wrapper(
    context: RunContextWrapper, agent: Agent, input_message: str | list[str]
) -> GuardrailFunctionOutput:
    return _evaluate_support_prefix_guardrail(input_message)


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
    def factory(selected_guardrail=require_support_prefix) -> Agency:
        agent = Agent(
            name="InputGuardrailAgent",
            instructions="You are a helpful assistant.",
            model="gpt-4o",
            input_guardrails=[selected_guardrail],
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
    assert "prefix your request with 'Support:'" in system_msgs[0].get("content", "")


def test_output_guardrail_logs_guidance(output_guardrail_agency: Agency):
    agency = output_guardrail_agency
    agency.get_response_sync(message="Hi")

    # History should contain a system guidance message from the guardrail
    all_msgs = agency.thread_manager.get_all_messages()
    system_msgs = [m for m in all_msgs if m.get("role") == "system"]
    assert any("Email addresses are not allowed" in (m.get("content", "")) for m in system_msgs)


def test_input_guardrail_multiple_agent_inits_no_double_wrap(input_guardrail_agency_factory):
    # Initialize Agents multiple times BEFORE sending any query to simulate repeated setup
    for _ in range(3):
        # guardrail_wrapper intentionally shares the wrapper name; this guards against name-based checks.
        agency = input_guardrail_agency_factory(guardrail_wrapper)

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
    assert "prefix your request with 'Support:'" in system_msgs[0].get("content", "")
