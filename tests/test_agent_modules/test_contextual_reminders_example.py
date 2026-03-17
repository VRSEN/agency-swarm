from examples.contextual_reminders import build_reminder_message, build_turn_input, create_demo_agency


def test_build_turn_input_includes_follow_up_from_agency_context() -> None:
    agency = create_demo_agency()
    agency.user_context["follow_up"] = {
        "owner": "Ava",
        "promise": "Send the renewal deck",
        "due": "Friday",
        "status": "open",
    }

    items = build_turn_input("What follow-up is still open?", agency.user_context)

    assert items[0]["role"] == "system"
    assert "Send the renewal deck" in items[0]["content"]
    assert items[1] == {"role": "user", "content": "What follow-up is still open?"}


def test_build_reminder_message_resets_checkpoint_counter() -> None:
    agency = create_demo_agency()
    agency.user_context["tool_calls_since_reminder"] = 15

    reminder = build_reminder_message(agency.user_context)

    assert "Checkpoint reminder" in reminder
    assert agency.user_context["tool_calls_since_reminder"] == 0
