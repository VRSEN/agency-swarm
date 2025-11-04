import pytest

from agency_swarm import (
    Agency,
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
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


@input_guardrail(name="RequireSupportPrefixNamedWrapper")
async def guardrail_wrapper(
    context: RunContextWrapper, agent: Agent, input_message: str | list[str]
) -> GuardrailFunctionOutput:
    assert isinstance(input_message, str), "guardrail_wrapper guardrail must receive a user text message"
    bad = not input_message.startswith("Support:")
    return GuardrailFunctionOutput(
        output_info=(
            "Named guardrail_wrapper requires prefixing requests with 'Support:' before continuing." if bad else ""
        ),
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
        model="gpt-5-mini",
        input_guardrails=[require_support_prefix],
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
            model="gpt-5-mini",
            input_guardrails=[require_support_prefix],
            throw_input_guardrail_error=False,
        )
        return Agency(agent)

    return factory


@pytest.fixture
def output_guardrail_agent() -> Agent:
    return Agent(
        name="OutputGuardrailAgent",
        instructions=("You are a helpful assistant. Respond with exactly 'foo@example.com' and nothing else."),
        model="gpt-5-mini",
        output_guardrails=[forbid_email_output],
        validation_attempts=1,
    )


@pytest.fixture
def output_guardrail_agency(output_guardrail_agent: Agent) -> Agency:
    return Agency(output_guardrail_agent)


@pytest.fixture
def named_wrapper_guardrail_agent() -> Agent:
    return Agent(
        name="NamedWrapperGuardrailAgent",
        instructions="You are a helpful assistant.",
        model="gpt-5-mini",
        input_guardrails=[guardrail_wrapper],
        throw_input_guardrail_error=False,
    )


@pytest.fixture
def named_wrapper_guardrail_agency(named_wrapper_guardrail_agent: Agent) -> Agency:
    return Agency(named_wrapper_guardrail_agent)


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


def test_input_guardrail_function_named_guardrail_wrapper_is_wrapped(
    named_wrapper_guardrail_agency: Agency,
):
    resp = named_wrapper_guardrail_agency.get_response_sync(message="Help me")

    assert isinstance(resp.final_output, str)
    assert "Named guardrail_wrapper requires prefixing requests" in resp.final_output

    all_msgs = named_wrapper_guardrail_agency.thread_manager.get_all_messages()
    system_msgs = [m for m in all_msgs if m.get("role") == "system"]
    assert len(system_msgs) == 1
    assert "Named guardrail_wrapper requires prefixing requests" in system_msgs[-1].get("content", "")
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


@pytest.mark.asyncio
async def test_input_guardrail_streaming_suppresses_tool_execution_from_history(input_guardrail_agency: Agency):
    """When input guardrail trips during streaming, tool calls should not persist to thread history.

    Mirrors SDK behavior from test_input_guardrail_streamed_does_not_save_assistant_message_to_session:
    the model may respond in parallel with guardrail evaluation, but results are suppressed.
    """
    agency = input_guardrail_agency
    stream = agency.get_response_stream(message="Hello there")

    async for _ in stream:
        pass

    result = await stream.wait_final_result()

    # Should return guardrail guidance (not model output)
    assert isinstance(result.final_output, str)
    assert "prefix your request with 'Support:'" in result.final_output

    # History should contain ONLY user message + system guardrail guidance
    all_msgs = agency.thread_manager.get_all_messages()
    assert len(all_msgs) == 2, f"Expected 2 messages (user + guidance), got {len(all_msgs)}: {all_msgs}"

    assert all_msgs[0].get("role") == "user"
    assert all_msgs[0].get("content") == "Hello there"

    assert all_msgs[1].get("role") == "system"
    assert "prefix your request with 'Support:'" in all_msgs[1].get("content", "")
    assert all_msgs[1].get("message_origin") == "input_guardrail_message"

    # No assistant messages, function calls, or reasoning items should persist
    assert not any(m.get("role") == "assistant" for m in all_msgs)
    assert not any(m.get("type") == "function_call" for m in all_msgs)
    assert not any(m.get("type") == "reasoning" for m in all_msgs)


@pytest.mark.asyncio
async def test_input_guardrail_streaming_suppresses_subagent_calls():
    """When input guardrail trips during streaming, sub-agent messages must also be suppressed.

    Validates cleanup handles delegation chains when parent guardrail trips while SendMessage
    call is already in flight.
    """
    from agency_swarm import function_tool

    @function_tool
    def helper_action(data: str) -> str:
        return f"HELPER_RESULT:{data}"

    helper_agent = Agent(
        name="HelperAgent",
        instructions="Call helper_action immediately with the user input.",
        model="gpt-5-mini",
        tools=[helper_action],
    )

    parent_agent = Agent(
        name="ParentAgent",
        instructions="Use send_message to ask HelperAgent to process the input.",
        model="gpt-5-mini",
        input_guardrails=[require_support_prefix],
        throw_input_guardrail_error=False,
    )

    agency = Agency(
        parent_agent,
        communication_flows=[(parent_agent, helper_agent)],
    )

    stream = agency.get_response_stream(message="Process this")
    async for _ in stream:
        pass

    result = await stream.wait_final_result()
    assert "prefix your request with 'Support:'" in result.final_output

    all_msgs = agency.thread_manager.get_all_messages()

    # Should only have user + guardrail guidance, no sub-agent messages
    assert len(all_msgs) == 2, f"Expected 2 messages, got {len(all_msgs)}: {all_msgs}"
    assert all_msgs[0].get("role") == "user"
    assert all_msgs[1].get("role") == "system"
    assert all_msgs[1].get("message_origin") == "input_guardrail_message"

    # Verify no HelperAgent messages leaked through
    assert not any(m.get("agent") == "HelperAgent" for m in all_msgs)
