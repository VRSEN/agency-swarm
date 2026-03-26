from agency_swarm import AfterEveryUserMessage, EveryNToolCalls, MasterContext, RunContextWrapper
from examples.system_reminders import (
    build_checkpoint_reminder,
    build_follow_up_reminder,
    create_demo_agency,
    preview_turn_input,
)


def test_preview_turn_input_uses_agent_system_reminders() -> None:
    agency = create_demo_agency()
    agency.user_context["follow_up"] = {
        "owner": "Ava",
        "promise": "Send the renewal deck",
        "due": "Friday",
        "status": "open",
    }

    items = preview_turn_input("What follow-up is still open?", agency)

    assert items[0]["role"] == "system"
    assert "Send the renewal deck" in items[0]["content"]
    assert items[1] == {"role": "user", "content": "What follow-up is still open?"}


def test_demo_agency_configures_both_public_reminder_types() -> None:
    agency = create_demo_agency()
    reminder_agent = agency.agents["ReminderAgent"]

    assert isinstance(reminder_agent.system_reminders[0], AfterEveryUserMessage)
    assert isinstance(reminder_agent.system_reminders[1], EveryNToolCalls)


def test_preview_checkpoint_renders_optional_tool_call_reminder() -> None:
    agency = create_demo_agency()
    agency.user_context["follow_up"] = {
        "owner": "Ava",
        "promise": "Send the renewal deck",
        "due": "Friday",
        "status": "open",
    }

    items = preview_turn_input("Draft a short customer update.", agency, include_checkpoint=True)

    assert "Stored follow-up: Send the renewal deck" in items[0]["content"]
    assert "Checkpoint reminder" in items[1]["content"]


def test_public_reminder_renderers_read_agency_context() -> None:
    agency = create_demo_agency()
    agency.user_context["follow_up"] = {
        "owner": "Ava",
        "promise": "Send the renewal deck",
        "due": "Friday",
        "status": "open",
    }
    reminder_agent = agency.agents["ReminderAgent"]
    preview_context = RunContextWrapper(
        MasterContext(
            thread_manager=agency.thread_manager,
            agents=agency.agents,
            user_context=agency.user_context,
            current_agent_name=reminder_agent.name,
        )
    )

    user_message_preview = build_follow_up_reminder(preview_context, reminder_agent)
    checkpoint_preview = build_checkpoint_reminder(preview_context, reminder_agent)

    assert "Send the renewal deck" in user_message_preview
    assert "Checkpoint reminder" in checkpoint_preview
