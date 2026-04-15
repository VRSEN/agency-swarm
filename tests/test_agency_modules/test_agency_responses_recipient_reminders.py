import pytest

from agency_swarm import Agency
from tests.test_agency_modules._response_test_helpers import CapturingAgent


@pytest.mark.asyncio
async def test_agency_get_response_adds_recipient_switch_reminder_after_handoff() -> None:
    """Adds recipient_reminder when previous user call used handoff and target agent changed."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentB", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentB", "callerAgent": None},
        ]
    )

    await agency.get_response("new request", recipient_agent="AgentA")

    assert isinstance(agent_a.last_message, list)
    assert agent_a.last_message[0]["message_origin"] == "recipient_reminder"
    assert (
        agent_a.last_message[0]["content"]
        == 'User has switched recipient agent. You are "AgentA". Please continue the task.'
    )
    assert agent_a.last_message[1] == {"role": "user", "content": "new request"}


@pytest.mark.asyncio
async def test_agency_get_response_skips_recipient_switch_reminder_without_switch_or_handoff() -> None:
    """Does not add recipient_reminder unless both handoff-use and recipient-switch are true."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentA", "callerAgent": None},
            {"role": "assistant", "content": "done", "agent": "AgentA", "callerAgent": None},
        ]
    )
    await agency.get_response("new request", recipient_agent="AgentB")
    assert isinstance(agent_b.last_message, str)

    agency.thread_manager.clear()
    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentA", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentA. Please continue the task.",
                "agent": "AgentA",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentA", "callerAgent": None},
        ]
    )
    await agency.get_response("same target", recipient_agent="AgentA")
    assert isinstance(agent_a.last_message, str)


@pytest.mark.asyncio
async def test_agency_get_response_adds_reminder_after_repeated_manual_switches() -> None:
    """Refreshes the active control reminder on each manual recipient switch."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agent_c = CapturingAgent("AgentC")
    agency = Agency(agent_a, agent_b, agent_c)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentB", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentB", "callerAgent": None},
        ]
    )

    await agency.get_response("switch to AgentA", recipient_agent="AgentA")
    assert isinstance(agent_a.last_message, list)
    assert agent_a.last_message[0]["message_origin"] == "recipient_reminder"

    await agency.get_response("switch to AgentC", recipient_agent="AgentC")

    assert isinstance(agent_c.last_message, list)
    assert agent_c.last_message[0]["message_origin"] == "recipient_reminder"
    assert (
        agent_c.last_message[0]["content"]
        == 'User has switched recipient agent. You are "AgentC". Please continue the task.'
    )
    assert agent_c.last_message[-1] == {"role": "user", "content": "switch to AgentC"}


@pytest.mark.asyncio
async def test_agency_get_response_adds_reminder_after_structured_switch_turn() -> None:
    """Structured user inputs should keep reminder chaining on later switches."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agent_c = CapturingAgent("AgentC")
    agency = Agency(agent_a, agent_b, agent_c)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentB", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentB", "callerAgent": None},
        ]
    )

    await agency.get_response(
        [
            {"role": "user", "content": "switch to AgentA"},
            {"role": "user", "content": "keep the same structured payload"},
        ],
        recipient_agent="AgentA",
    )
    await agency.get_response("switch to AgentC", recipient_agent="AgentC")

    assert isinstance(agent_c.last_message, list)
    assert agent_c.last_message[0]["message_origin"] == "recipient_reminder"
    assert agent_c.last_message[-1] == {"role": "user", "content": "switch to AgentC"}


@pytest.mark.asyncio
async def test_agency_get_response_adds_reminder_after_split_run_handoff_turn() -> None:
    """Split top-level run ids should still preserve handoff reminder chaining."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agent_c = CapturingAgent("AgentC")
    agency = Agency(agent_a, agent_b, agent_c)

    agency.thread_manager.add_messages(
        [
            {
                "role": "user",
                "content": "previous",
                "agent": "AgentA",
                "callerAgent": None,
                "agent_run_id": "top-run",
            },
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentA",
                "callerAgent": None,
                "agent_run_id": "top-run",
                "message_origin": "handoff_reminder",
            },
            {
                "role": "assistant",
                "content": "done",
                "agent": "AgentB",
                "callerAgent": None,
                "agent_run_id": "handoff-run",
                "parent_run_id": "top-run",
            },
        ]
    )

    await agency.get_response("switch to AgentC", recipient_agent="AgentC")

    assert isinstance(agent_c.last_message, list)
    assert agent_c.last_message[0]["message_origin"] == "recipient_reminder"
    assert agent_c.last_message[-1] == {"role": "user", "content": "switch to AgentC"}


@pytest.mark.asyncio
async def test_agency_get_response_adds_reminder_after_interrupted_handoff_turn() -> None:
    """Manual switches should still refresh control when the prior handoff never answered."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentA", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentA",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
        ]
    )

    await agency.get_response("switch to AgentB", recipient_agent="AgentB")

    assert isinstance(agent_b.last_message, list)
    assert agent_b.last_message[0]["message_origin"] == "recipient_reminder"
    assert agent_b.last_message[-1] == {"role": "user", "content": "switch to AgentB"}


@pytest.mark.asyncio
async def test_agency_get_response_adds_reminder_when_interrupted_handoff_switches_back() -> None:
    """Interrupted handoffs should refresh control even when switching back to the original agent."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentA", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentA",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
        ]
    )

    await agency.get_response("switch back to AgentA", recipient_agent="AgentA")

    assert isinstance(agent_a.last_message, list)
    assert agent_a.last_message[0]["message_origin"] == "recipient_reminder"
    assert agent_a.last_message[-1] == {"role": "user", "content": "switch back to AgentA"}


@pytest.mark.asyncio
async def test_agency_get_response_accepts_legacy_top_level_reminder_in_split_run_turn() -> None:
    """Split-run histories should still honor top-level reminders that predate run ids."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {
                "role": "user",
                "content": "top-level request",
                "agent": "AgentA",
                "callerAgent": None,
                "agent_run_id": "top-run",
            },
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {
                "role": "assistant",
                "content": "done",
                "agent": "AgentB",
                "callerAgent": None,
                "agent_run_id": "handoff-run",
                "parent_run_id": "top-run",
            },
        ]
    )

    await agency.get_response("switch to AgentA", recipient_agent="AgentA")

    assert isinstance(agent_a.last_message, list)
    assert agent_a.last_message[0]["message_origin"] == "recipient_reminder"
    assert agent_a.last_message[-1] == {"role": "user", "content": "switch to AgentA"}


@pytest.mark.asyncio
async def test_agency_get_response_stream_adds_recipient_switch_reminder_after_handoff() -> None:
    """Streaming path should prepend recipient_reminder under the same conditions."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentB", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": None,
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentB", "callerAgent": None},
        ]
    )

    stream = agency.get_response_stream("new request", recipient_agent="AgentA")
    async for _event in stream:
        pass

    assert isinstance(agent_a.last_message, list)
    assert agent_a.last_message[0]["message_origin"] == "recipient_reminder"


@pytest.mark.asyncio
async def test_agency_get_response_stream_keeps_empty_input_guard_when_reminder_would_apply() -> None:
    """Streaming empty-input validation should still win over reminder injection."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "previous", "agent": "AgentB", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are AgentB. Please continue the task.",
                "agent": "AgentB",
                "callerAgent": "AgentA",
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "done", "agent": "AgentB", "callerAgent": None},
        ]
    )

    events = []
    stream = agency.get_response_stream("   ", recipient_agent="AgentA")
    async for event in stream:
        events.append(event)

    assert stream.final_result is None
    assert events == [{"type": "error", "content": "message cannot be empty"}]
    assert agent_a.last_message == "   "


@pytest.mark.asyncio
async def test_agency_get_response_ignores_descendant_handoff_reminders_from_other_runs() -> None:
    """Child-run handoff reminders should not trigger user-thread recipient reminders."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {
                "role": "user",
                "content": "top-level request",
                "agent": "AgentA",
                "callerAgent": None,
                "agent_run_id": "top-run",
            },
            {
                "role": "assistant",
                "content": "top-level response",
                "agent": "AgentA",
                "callerAgent": None,
                "agent_run_id": "top-run",
            },
            {
                "role": "system",
                "content": "Transfer completed. You are Specialist. Please continue the task.",
                "agent": "Specialist",
                "callerAgent": "AgentA",
                "agent_run_id": "child-run",
                "message_origin": "handoff_reminder",
            },
            {
                "role": "assistant",
                "content": "child response",
                "agent": "Specialist",
                "callerAgent": "AgentA",
                "agent_run_id": "child-run",
            },
        ]
    )

    await agency.get_response("new top-level switch", recipient_agent="AgentB")

    assert agent_b.last_message == "new top-level switch"


@pytest.mark.asyncio
async def test_agency_get_response_ignores_legacy_child_handoff_reminders_without_run_ids() -> None:
    """Legacy histories without run ids should only trust user-thread reminders."""
    agent_a = CapturingAgent("AgentA")
    agent_b = CapturingAgent("AgentB")
    agency = Agency(agent_a, agent_b)

    agency.thread_manager.add_messages(
        [
            {"role": "user", "content": "top-level request", "agent": "AgentA", "callerAgent": None},
            {"role": "assistant", "content": "top-level response", "agent": "AgentA", "callerAgent": None},
            {
                "role": "system",
                "content": "Transfer completed. You are Specialist. Please continue the task.",
                "agent": "Specialist",
                "callerAgent": "AgentA",
                "message_origin": "handoff_reminder",
            },
            {"role": "assistant", "content": "child response", "agent": "Specialist", "callerAgent": "AgentA"},
        ]
    )

    await agency.get_response("new legacy switch", recipient_agent="AgentB")

    assert agent_b.last_message == "new legacy switch"
