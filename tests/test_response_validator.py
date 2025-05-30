import json
import re
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import BaseModel, Field

from agency_swarm import Agent
from agency_swarm.messages import MessageOutput
from agency_swarm.threads.thread import Thread
from agency_swarm.user import User


@pytest.fixture
def thread_and_agent():
    """Create a properly mocked thread and agent for testing."""
    mock_client = Mock()
    mock_user = User()
    test_agent = Agent(name="TestAgent", description="Test agent for validation", instructions="Test instructions")
    thread = Thread(mock_user, test_agent)
    thread.client = mock_client
    thread.id = "test_thread_id"
    thread._thread = Mock()
    thread._run = Mock()
    thread._run.id = "test_run_id"

    # Mock the create_message method to return a realistic message object
    mock_message = Mock()
    mock_message.content = [Mock()]
    mock_message.content[0].text = Mock()
    thread.create_message = Mock(return_value=mock_message)
    thread._create_run = Mock()

    return thread, test_agent


class TestResponseValidatorCore:
    """Test the core validation functionality."""

    def test_no_validator_returns_none(self, thread_and_agent):
        """Test that no validation is performed when no validator is set."""
        thread, agent = thread_and_agent
        agent.response_validator = None

        result = thread._validate_assistant_response(
            recipient_agent=agent,
            last_message="Any message",
            validation_attempts=0,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )
        assert result is None

    def test_successful_validation_returns_none(self, thread_and_agent):
        """Test that successful validation returns None (continue normally)."""
        thread, agent = thread_and_agent

        def passing_validator(message: str) -> str:
            return message

        agent.response_validator = passing_validator
        agent.validation_attempts = 2

        result = thread._validate_assistant_response(
            recipient_agent=agent,
            last_message="Valid message",
            validation_attempts=0,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )
        assert result is None

    def test_validation_failure_with_retries_available(self, thread_and_agent):
        """Test validation failure with retries still available."""
        thread, agent = thread_and_agent

        def failing_validator(message: str) -> str:
            raise ValueError("Validation failed: Please include keyword 'VALID'")

        agent.response_validator = failing_validator
        agent.validation_attempts = 3

        # Mock message creation
        thread.create_message.return_value.content[0].text.value = "Validation failed: Please include keyword 'VALID'"

        result = thread._validate_assistant_response(
            recipient_agent=agent,
            last_message="Invalid message",
            validation_attempts=1,  # Still have retries left (1 < 3)
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )

        # Should return retry info
        assert result is not None
        assert result["continue_loop"] is True
        assert result["validation_attempts"] == 2
        assert "message_outputs" in result

        # Verify error message was sent to thread
        thread.create_message.assert_called_once_with(
            message="Validation failed: Please include keyword 'VALID'", role="user"
        )
        thread._create_run.assert_called_once()

    def test_validation_failure_retries_exhausted_raises_exception(self, thread_and_agent):
        """Test that validation raises exception when retries are exhausted."""
        thread, agent = thread_and_agent

        def failing_validator(message: str) -> str:
            raise ValueError("Validation failed: Critical error")

        agent.response_validator = failing_validator
        agent.validation_attempts = 2

        with pytest.raises(ValueError) as excinfo:
            thread._validate_assistant_response(
                recipient_agent=agent,
                last_message="Invalid message",
                validation_attempts=2,  # Exceeded limit (2 >= 2)
                yield_messages=False,
                additional_instructions=None,
                event_handler=None,
                tool_choice=None,
                response_format=None,
            )

        assert str(excinfo.value) == "Validation failed: Critical error"
        # Should not create message or run when retries exhausted
        thread.create_message.assert_not_called()
        thread._create_run.assert_not_called()


class TestResponseValidatorEdgeCases:
    """Test edge cases and specific error types."""

    def test_different_exception_types_preserved(self, thread_and_agent):
        """Test that different exception types are preserved correctly."""
        thread, agent = thread_and_agent

        # Test SyntaxError
        def syntax_error_validator(message: str) -> str:
            raise SyntaxError("unterminated string literal")

        agent.response_validator = syntax_error_validator
        agent.validation_attempts = 1

        with pytest.raises(SyntaxError) as excinfo:
            thread._validate_assistant_response(
                recipient_agent=agent,
                last_message="test",
                validation_attempts=1,
                yield_messages=False,
                additional_instructions=None,
                event_handler=None,
                tool_choice=None,
                response_format=None,
            )
        assert "unterminated string literal" in str(excinfo.value)

        # Test custom exception
        class CustomValidationError(Exception):
            pass

        def custom_error_validator(message: str) -> str:
            raise CustomValidationError("Custom validation failure")

        agent.response_validator = custom_error_validator

        with pytest.raises(CustomValidationError) as excinfo:
            thread._validate_assistant_response(
                recipient_agent=agent,
                last_message="test",
                validation_attempts=1,
                yield_messages=False,
                additional_instructions=None,
                event_handler=None,
                tool_choice=None,
                response_format=None,
            )
        assert "Custom validation failure" in str(excinfo.value)

    def test_yield_messages_functionality(self, thread_and_agent):
        """Test that message outputs are properly yielded when yield_messages=True."""
        thread, agent = thread_and_agent

        def failing_validator(message: str) -> str:
            raise ValueError("Please fix this")

        agent.response_validator = failing_validator
        agent.validation_attempts = 3

        # Setup mock message with text content
        thread.create_message.return_value.content[0].text.value = "Please fix this"

        result = thread._validate_assistant_response(
            recipient_agent=agent,
            last_message="Invalid",
            validation_attempts=1,
            yield_messages=True,  # Enable message yielding
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )

        assert result is not None
        assert result["continue_loop"] is True
        assert len(result["message_outputs"]) == 1

        message_output = result["message_outputs"][0]
        assert isinstance(message_output, MessageOutput)
        assert message_output.msg_type == "text"
        assert message_output.sender_name == "User"  # User sends validation error
        assert message_output.receiver_name == "TestAgent"
        assert message_output.content == "Please fix this"


class TestRealisticScenarios:
    """Test realistic validation scenarios that might be used in production."""

    def test_json_format_validation(self, thread_and_agent):
        """Test realistic JSON format validation."""
        thread, agent = thread_and_agent

        def json_validator(message: str) -> str:
            try:
                data = json.loads(message)
                if not isinstance(data, dict):
                    raise ValueError("Response must be a JSON object")
                if "status" not in data:
                    raise ValueError("Response must include 'status' field")
                return message
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON format: {message}")

        agent.response_validator = json_validator
        agent.validation_attempts = 1

        # Test invalid JSON
        with pytest.raises(ValueError) as excinfo:
            thread._validate_assistant_response(
                recipient_agent=agent,
                last_message='{"incomplete": json',
                validation_attempts=1,
                yield_messages=False,
                additional_instructions=None,
                event_handler=None,
                tool_choice=None,
                response_format=None,
            )
        assert "Invalid JSON format" in str(excinfo.value)

        # Test missing required field
        with pytest.raises(ValueError) as excinfo:
            thread._validate_assistant_response(
                recipient_agent=agent,
                last_message='{"data": "test"}',
                validation_attempts=1,
                yield_messages=False,
                additional_instructions=None,
                event_handler=None,
                tool_choice=None,
                response_format=None,
            )
        assert "must include 'status' field" in str(excinfo.value)

        # Test valid JSON
        result = thread._validate_assistant_response(
            recipient_agent=agent,
            last_message='{"status": "success", "data": "test"}',
            validation_attempts=0,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )
        assert result is None  # Validation passed

    def test_content_policy_validation(self, thread_and_agent):
        """Test content policy validation."""
        thread, agent = thread_and_agent

        forbidden_words = ["password", "secret", "confidential"]

        def content_policy_validator(message: str) -> str:
            message_lower = message.lower()
            for word in forbidden_words:
                if word in message_lower:
                    raise ValueError(
                        f"Response contains forbidden word: '{word}'. Please rephrase without sensitive information."
                    )
            return message

        agent.response_validator = content_policy_validator
        agent.validation_attempts = 2

        # Test forbidden content
        thread.create_message.return_value.content[
            0
        ].text.value = "Response contains forbidden word: 'password'. Please rephrase without sensitive information."

        result = thread._validate_assistant_response(
            recipient_agent=agent,
            last_message="The password is 12345",
            validation_attempts=0,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )

        assert result is not None
        assert result["continue_loop"] is True
        assert "forbidden word: 'password'" in thread.create_message.call_args[1]["message"]

        # Test allowed content
        result = thread._validate_assistant_response(
            recipient_agent=agent,
            last_message="Here is the public information you requested",
            validation_attempts=0,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )
        assert result is None  # Validation passed

    def test_pydantic_model_validation(self, thread_and_agent):
        """Test validation using Pydantic models."""
        thread, agent = thread_and_agent

        class ResponseModel(BaseModel):
            action: str = Field(..., description="The action taken")
            result: str = Field(..., description="The result of the action")
            confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")

        def pydantic_validator(message: str) -> str:
            try:
                data = json.loads(message)
                ResponseModel(**data)  # Validate against Pydantic model
                return message
            except json.JSONDecodeError:
                raise ValueError("Response must be valid JSON")
            except Exception as e:
                raise ValueError(f"Response validation failed: {str(e)}")

        agent.response_validator = pydantic_validator
        agent.validation_attempts = 1

        # Test invalid data (missing fields)
        with pytest.raises(ValueError) as excinfo:
            thread._validate_assistant_response(
                recipient_agent=agent,
                last_message='{"action": "test"}',
                validation_attempts=1,
                yield_messages=False,
                additional_instructions=None,
                event_handler=None,
                tool_choice=None,
                response_format=None,
            )
        assert "validation failed" in str(excinfo.value)

        # Test invalid confidence range
        with pytest.raises(ValueError) as excinfo:
            thread._validate_assistant_response(
                recipient_agent=agent,
                last_message='{"action": "test", "result": "success", "confidence": 1.5}',
                validation_attempts=1,
                yield_messages=False,
                additional_instructions=None,
                event_handler=None,
                tool_choice=None,
                response_format=None,
            )
        assert "validation failed" in str(excinfo.value)

        # Test valid data
        result = thread._validate_assistant_response(
            recipient_agent=agent,
            last_message='{"action": "test", "result": "success", "confidence": 0.95}',
            validation_attempts=0,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )
        assert result is None  # Validation passed


class TestEventHandlerIntegration:
    """Test validation with event handlers."""

    def test_event_handler_called_during_validation_retry(self, thread_and_agent):
        """Test that event handlers are properly called during validation retries."""
        thread, agent = thread_and_agent

        def failing_validator(message: str) -> str:
            raise ValueError("Validation error for testing")

        agent.response_validator = failing_validator
        agent.validation_attempts = 3

        # Create mock event handler
        mock_event_handler = Mock()
        mock_handler_instance = Mock()
        mock_event_handler.return_value = mock_handler_instance

        thread.create_message.return_value.content[0].text.value = "Validation error for testing"

        result = thread._validate_assistant_response(
            recipient_agent=agent,
            last_message="Invalid",
            validation_attempts=1,
            yield_messages=False,
            additional_instructions=None,
            event_handler=mock_event_handler,
            tool_choice=None,
            response_format=None,
        )

        assert result is not None
        assert result["continue_loop"] is True

        # Verify event handler was called
        mock_event_handler.assert_called_once()
        mock_handler_instance.on_message_created.assert_called_once()
        mock_handler_instance.on_message_done.assert_called_once()


class TestRegressionTests:
    """Tests specifically for the bugs that were fixed."""

    def test_no_eval_corruption(self, thread_and_agent):
        """Test that eval() is no longer used and error messages are preserved."""
        thread, agent = thread_and_agent

        # Create a validation error that would break eval()
        dangerous_message = "raise Exception('This would be executed by eval')"

        def validator_with_dangerous_error(message: str) -> str:
            raise ValueError(dangerous_message)

        agent.response_validator = validator_with_dangerous_error
        agent.validation_attempts = 2

        thread.create_message.return_value.content[0].text.value = dangerous_message

        result = thread._validate_assistant_response(
            recipient_agent=agent,
            last_message="test",
            validation_attempts=0,
            yield_messages=False,
            additional_instructions=None,
            event_handler=None,
            tool_choice=None,
            response_format=None,
        )

        # Verify the dangerous message was passed as-is, not eval'd
        thread.create_message.assert_called_once_with(message=dangerous_message, role="user")
        assert result["continue_loop"] is True

    def test_exception_raising_not_swallowed(self, thread_and_agent):
        """Test that exceptions are properly raised when retries are exhausted."""
        thread, agent = thread_and_agent

        original_error = ValueError("Original validation error")

        def failing_validator(message: str) -> str:
            raise original_error

        agent.response_validator = failing_validator
        agent.validation_attempts = 1

        # This should raise the original exception, not swallow it
        with pytest.raises(ValueError) as excinfo:
            thread._validate_assistant_response(
                recipient_agent=agent,
                last_message="test",
                validation_attempts=1,  # Exhausted (1 >= 1)
                yield_messages=False,
                additional_instructions=None,
                event_handler=None,
                tool_choice=None,
                response_format=None,
            )

        # Verify the exact same exception is raised
        assert excinfo.value is original_error
        assert str(excinfo.value) == "Original validation error"
