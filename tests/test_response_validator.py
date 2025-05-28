import json
from unittest.mock import Mock

import pytest
from pydantic import BaseModel, Field

from agency_swarm import Agent
from agency_swarm.threads.thread import Thread
from agency_swarm.user import User


@pytest.fixture
def thread_and_agent():
    mock_client = Mock()
    mock_user = User()
    test_agent = Agent(name="TestAgent", description="Test agent for validation", instructions="Test instructions")
    thread = Thread(mock_user, test_agent)
    thread.client = mock_client
    thread.id = "test_thread_id"
    thread._thread = Mock()
    thread._run = Mock()
    thread._run.id = "test_run_id"
    return thread, test_agent


def test_validation_exception_raised_when_retries_exceeded_value_error(thread_and_agent):
    thread, test_agent = thread_and_agent

    def failing_validator(message):
        raise ValueError("Validation failed: Invalid response format")

    test_agent.response_validator = failing_validator
    test_agent.validation_attempts = 2

    with pytest.raises(ValueError) as excinfo:
        thread._validate_assistant_response(
            recipient_agent=test_agent,
            last_message="Invalid message",
            validation_attempts=2,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )
    assert str(excinfo.value) == "Validation failed: Invalid response format"


def test_validation_exception_raised_when_retries_exceeded_syntax_error(thread_and_agent):
    thread, test_agent = thread_and_agent

    def failing_validator_with_syntax_error(message):
        raise SyntaxError("unterminated string literal (detected at line 1)")

    test_agent.response_validator = failing_validator_with_syntax_error
    test_agent.validation_attempts = 1

    with pytest.raises(SyntaxError) as excinfo:
        thread._validate_assistant_response(
            recipient_agent=test_agent,
            last_message="Malformed JSON response",
            validation_attempts=1,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )
    assert str(excinfo.value) == "unterminated string literal (detected at line 1)"


def test_validation_exception_raised_when_retries_exceeded_json_decode_error(thread_and_agent):
    thread, test_agent = thread_and_agent

    def failing_validator_with_json_error(message):
        if isinstance(message, str):
            try:
                json.loads(message)
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON message format: {message}")

    test_agent.response_validator = failing_validator_with_json_error
    test_agent.validation_attempts = 1

    with pytest.raises(ValueError) as excinfo:
        thread._validate_assistant_response(
            recipient_agent=test_agent,
            last_message="invalid json {",
            validation_attempts=1,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )
    assert "Invalid JSON message format" in str(excinfo.value)


def test_validation_retry_logic_works_when_attempts_available(thread_and_agent):
    thread, test_agent = thread_and_agent

    def failing_validator(message):
        raise ValueError("Validation failed: Invalid response format")

    test_agent.response_validator = failing_validator
    test_agent.validation_attempts = 3

    mock_message = Mock()
    mock_message.content = [Mock()]
    mock_message.content[0].text = Mock()
    mock_message.content[0].text.value = "Validation failed: Invalid response format"
    thread.create_message = Mock(return_value=mock_message)
    thread._create_run = Mock()

    result = thread._validate_assistant_response(
        recipient_agent=test_agent,
        last_message="Invalid message",
        validation_attempts=1,
        yield_messages=False,
        additional_instructions=None,
        event_handler=None,
        tool_choice=None,
        response_format=None,
    )
    assert result is not None
    assert result["continue_loop"]
    assert result["validation_attempts"] == 2


def test_validation_passes_when_no_validator_present(thread_and_agent):
    thread, test_agent = thread_and_agent

    test_agent.response_validator = None

    result = thread._validate_assistant_response(
        recipient_agent=test_agent,
        last_message="Any message",
        validation_attempts=0,
        yield_messages=False,
        additional_instructions=None,
        event_handler=None,
        tool_choice=None,
        response_format=None,
    )
    assert result is None


def test_validation_passes_when_validator_succeeds(thread_and_agent):
    thread, test_agent = thread_and_agent

    def successful_validator(message):
        return True

    test_agent.response_validator = successful_validator
    test_agent.validation_attempts = 2

    result = thread._validate_assistant_response(
        recipient_agent=test_agent,
        last_message="Valid message",
        validation_attempts=0,
        yield_messages=False,
        additional_instructions=None,
        event_handler=None,
        tool_choice=None,
        response_format=None,
    )
    assert result is None


def test_realistic_json_validation_scenario(thread_and_agent):
    thread, test_agent = thread_and_agent

    class ResponseStructure(BaseModel):
        name: str = Field(..., description="Agent name")
        text: str = Field(..., description="Response text")

    def realistic_validator(message):
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON message format: {message}")
        if message.get("name") != "TestAgent":
            raise ValueError(
                f"Incorrect agent identifier in name attribute of message. Expected 'TestAgent', but got '{message.get('name')}'."
            )
        return True

    test_agent.response_validator = realistic_validator
    test_agent.validation_attempts = 2

    with pytest.raises(ValueError) as excinfo:
        thread._validate_assistant_response(
            recipient_agent=test_agent,
            last_message='{"name": "TestAgent", "text": "unterminated string',
            validation_attempts=2,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )
    assert "Invalid JSON message format" in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo:
        thread._validate_assistant_response(
            recipient_agent=test_agent,
            last_message='{"name": "WrongAgent", "text": "Some response"}',
            validation_attempts=2,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )
    assert "Incorrect agent identifier" in str(excinfo.value)


def test_validation_retry_with_yield_messages(thread_and_agent):
    thread, test_agent = thread_and_agent

    def failing_validator(message):
        raise ValueError("Validation failed: Invalid format")

    test_agent.response_validator = failing_validator
    test_agent.validation_attempts = 3

    mock_message = Mock()
    mock_message.content = [Mock()]
    mock_message.content[0].text = Mock()
    mock_message.content[0].text.value = "Validation failed: Invalid format"
    thread.create_message = Mock(return_value=mock_message)
    thread._create_run = Mock()

    result = thread._validate_assistant_response(
        recipient_agent=test_agent,
        last_message="Invalid message",
        validation_attempts=1,
        yield_messages=True,
        additional_instructions=None,
        event_handler=None,
        tool_choice=None,
        response_format=None,
    )
    assert result is not None
    assert result["continue_loop"]
    assert result["validation_attempts"] == 2
    assert isinstance(result["message_outputs"], list)
