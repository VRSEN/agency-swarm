from agency_swarm import AfterEveryUserMessage
from examples.system_reminders import REMINDER_TEXT, create_demo_agency, show_setup


def test_demo_agency_configures_one_beginner_reminder() -> None:
    agency = create_demo_agency()
    reminder_agent = agency.agents["ReminderAgent"]

    assert reminder_agent.tools == []
    assert len(reminder_agent.system_reminders) == 1
    assert isinstance(reminder_agent.system_reminders[0], AfterEveryUserMessage)
    assert reminder_agent.system_reminders[0].message == REMINDER_TEXT


def test_show_setup_explains_the_simple_starting_point(capsys) -> None:
    show_setup()
    output = capsys.readouterr().out

    assert "System Reminders Demo" in output
    assert REMINDER_TEXT in output
    assert "OPENAI_API_KEY" in output
