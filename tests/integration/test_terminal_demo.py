"""
Test suite using pytest's capsys for output capture with Agency.

This approach uses pytest's built-in capsys fixture to capture output
of the terminal.
"""

from unittest.mock import patch

import pytest
from agents import ModelSettings
from prompt_toolkit.document import Document

from agency_swarm import Agency, Agent
from agency_swarm.tools.send_message import SendMessageHandoff
from agency_swarm.ui.demos import terminal as terminal_module
from agency_swarm.ui.demos.terminal import start_terminal


class MockInputProvider:
    """Provides sequential input responses for testing."""

    def __init__(self, inputs: list[str]):
        self.inputs = inputs
        self.index = 0

    def __call__(self, prompt=""):
        """Mock input function that returns sequential inputs."""
        if self.index < len(self.inputs):
            result = self.inputs[self.index]
            self.index += 1
            # Echo input to simulate terminal behavior
            print(f"{prompt}{result}")
            return result
        return "/exit"

    async def async_call(self, prompt="", **kwargs):
        """Mock async prompt for prompt_toolkit."""
        return self(prompt)


def _application_factory(provider: MockInputProvider):
    """Return a PromptToolkit Application stub that replays provider inputs."""

    class _ApplicationStub:
        def __init__(self, *args, **kwargs):
            self._provider = provider
            self._layout = kwargs.get("layout")

        def invalidate(self) -> None:  # noqa: D401 - simple no-op
            """No-op invalidate used by dropdown integration."""

        async def run_async(self):  # noqa: ANN201 - signature mirrors prompt_toolkit
            value = await self._provider.async_call()
            if value is None:
                value = "/exit"
            buffer = getattr(self._layout, "current_buffer", None)
            if buffer is not None:
                buffer.document = Document(value, len(value))
            return value

    return _ApplicationStub


@pytest.fixture
def agency():
    """Create an agency for testing."""
    test_agent = Agent(
        name="TestAgent",
        description="A test agent for terminal testing",
        instructions=(
            "You are a helpful test assistant. Keep responses very brief (max 10 words). "
            "Always respond with 'Test response: [user message]'. "
            "You can hand off to the Developer agent by using transfer_to_ tool."
        ),
        model_settings=ModelSettings(temperature=0),
    )

    developer_agent = Agent(
        name="Developer",
        description="A developer agent",
        instructions="You are a developer. Respond with 'Dev response: [message]'.",
        model_settings=ModelSettings(temperature=0),
    )

    # Agent with a bad formatted name
    security_expert_agent = Agent(
        name="SecUrity ExperT_Agent",
        description="A security expert agent",
        instructions="You are a security expert. Respond with 'Security expert response: [message]'.",
        model_settings=ModelSettings(temperature=0),
    )

    agency = Agency(
        test_agent,
        developer_agent,
        security_expert_agent,
        communication_flows=[
            (security_expert_agent < test_agent > developer_agent, SendMessageHandoff),
        ],
        name="TestAgency",
        shared_instructions="This is a test agency. Keep all responses very brief.",
    )

    return agency


class TestTerminalCapsys:
    """Test terminal demo using capsys for output capture."""

    def test_help_command_output(self, agency, capsys):
        """Test /help command output capture."""
        input_provider = MockInputProvider(["/help", "/exit"])

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)

        captured = capsys.readouterr()
        output = captured.out
        assert "/help" in output
        assert "/new" in output
        assert "/compact" in output
        assert "/resume" in output
        assert "/status" in output
        assert "/exit" in output

    def test_status_command_output(self, agency, capsys):
        """Test /status command output capture."""
        input_provider = MockInputProvider(["/status", "/exit"])

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)

        captured = capsys.readouterr()
        output = captured.out
        assert "Agency: TestAgency" in output
        assert "Entry Points: TestAgent" in output
        assert "Default Recipient: TestAgent" in output
        assert "cwd:" in output

    def test_new_command_functionality(self, agency, capsys):
        """Test /new command functionality."""
        input_provider = MockInputProvider(["/new", "/exit"])

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)

        captured = capsys.readouterr()
        output = captured.out
        assert "Started a new chat session" in output

    def test_message_sending_and_response(self, agency, capsys):
        """Test sending message and receiving response from agent."""
        input_provider = MockInputProvider(["Hello world", "/exit"])

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)

        captured = capsys.readouterr()
        output = captured.out

        assert "Hello world" in output
        assert "🤖 TestAgent → 👤 user" in output
        assert "Test response:" in output

    def test_agent_mention_parsing(self, agency, capsys):
        """Test @agent mention parsing with multi-agent setup."""
        input_provider = MockInputProvider(["@Developer help me", "/exit"])

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)

        captured = capsys.readouterr()
        output = captured.out

        assert "🤖 Developer → 👤 user" in output
        assert "Dev response:" in output

    def test_empty_input_handling(self, agency, capsys):
        """Test handling of empty input."""
        input_provider = MockInputProvider(["", "   ", "/exit"])

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)

        captured = capsys.readouterr()
        assert "message cannot be empty" in captured.out

    def test_handoff_chat_transfer(self, agency, capsys):
        """Test handoff chat transfer."""
        input_provider = MockInputProvider(["Transfer to Developer", "Hi", "/exit"])

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)

        captured = capsys.readouterr()
        output = captured.out

        # Verify that initial input is sent to main agent
        assert "🤖 TestAgent 🛠️ Executing Function"
        assert "Calling transfer_to_Developer tool with:" in output

        # Verify that after handoff, response is sent by developer
        assert "🤖 Developer → 👤 user" in output
        assert "Dev response:" in output

        # Verify that next input went to developer
        assert "🤖 Developer → 👤 user" in output.split("USER: Hi")[-1]
        assert "Dev response:" in output.split("USER: Hi")[-1]

    def test_slash_dropdown_populates_commands(self, agency):
        """Ensure slash input populates dropdown items."""
        input_provider = MockInputProvider(["/", "/exit"])
        captured_labels: list[list[str]] = []

        original_set_items = terminal_module.DropdownMenu.set_items

        def _capture(self, items):  # noqa: ANN001
            captured_labels.append([item.label for item in items])
            original_set_items(self, items)

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                with patch.object(terminal_module.DropdownMenu, "set_items", _capture):
                    start_terminal(agency, reload=False)

        assert captured_labels, "Expected dropdown items to be set"
        assert any(label.startswith("/") for label in captured_labels[0])


class TestTerminalEdgeCases:
    """Test edge cases and error handling with agency."""

    def test_invalid_agent_mention_logs_error(self, agency, capsys, caplog):
        """Test that invalid @agent mentions are logged as errors."""
        input_provider = MockInputProvider(["@NonExistentAgent help", "/exit"])

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)

        # Check that error was logged
        assert "Recipient agent NonExistentAgent not found" in caplog.text

    def test_very_long_message(self, agency, capsys):
        """Test handling of very long messages."""
        long_message = "This is a very long message. " * 50
        input_provider = MockInputProvider([long_message, "/exit"])

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)

        captured = capsys.readouterr()
        assert "🤖 TestAgent → 👤 user" in captured.out
        assert "Test response:" in captured.out

    def test_special_characters_in_message(self, agency, capsys):
        """Test handling of special characters in messages."""
        special_message = "Test with émojis 🎉 and symbols @#$%!"
        input_provider = MockInputProvider([special_message, "/exit"])

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)

        captured = capsys.readouterr()
        assert "🤖 TestAgent → 👤 user" in captured.out
        assert "Test response: Test with émojis 🎉 and symbols @#$%!" in captured.out

    def test_bad_formatted_agent_name(self, agency, capsys):
        """Test handling of bad formatted agent name."""
        input_provider = MockInputProvider(["@SecUrity ExperT_Agent hi", "/exit"])
        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)
        captured = capsys.readouterr()
        assert "🤖 SecUrity ExperT_Agent → 👤 user" in captured.out
        assert "Security expert response:" in captured.out

    def test_bad_formatted_agent_name_handoff(self, agency, capsys):
        """Test handling of bad formatted agent name."""
        input_provider = MockInputProvider(["Use the transfer_to_Security_Expert_Agent tool", "Hi", "/exit"])

        with patch("builtins.input", input_provider):
            with patch("agency_swarm.ui.demos.terminal.Application", new=_application_factory(input_provider)):
                start_terminal(agency, reload=False)

        captured = capsys.readouterr()
        output = captured.out

        # Handoffs will replace spaces with underscores
        assert "🤖 TestAgent 🛠️ Executing Function"
        assert "Calling transfer_to_SecUrity_ExperT_Agent tool with:" in output

        # Verify that after handoff, name is shown correctly
        assert "🤖 SecUrity ExperT_Agent → 👤 user" in output
        assert "Security expert response:" in output

        # Verify that next input went didn't cause any errors
        assert "🤖 SecUrity ExperT_Agent → 👤 user" in output.split("USER: Hi")[-1]
        assert "Security expert response:" in output.split("USER: Hi")[-1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
