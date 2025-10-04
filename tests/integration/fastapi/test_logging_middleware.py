"""
Integration tests for FastAPI logging middleware.

Tests the actual logging behavior, request tracking, file operations,
and HTTP middleware functionality.
"""

import asyncio
import json
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

os.environ.setdefault("OPENAI_AGENTS_DISABLE_TRACING", "1")

from agents import ModelSettings
from agents.tracing import set_tracing_disabled

from agency_swarm import Agency, Agent, run_fastapi
from agency_swarm.integrations.fastapi_utils.logging_middleware import (
    ConditionalFileHandler,
    ConsoleFormatter,
    FileFormatter,
    RequestTracker,
    get_log_id_from_headers,
    get_logs_endpoint_impl,
    log_to_file_context,
    request_id_context,
    setup_enhanced_logging,
)


@contextmanager
def set_context(var, value):
    """Temporarily set a ContextVar value."""

    token = var.set(value)
    try:
        yield
    finally:
        var.reset(token)


@pytest.fixture(autouse=True)
def ensure_clean_logging_context():
    """Ensure logging ContextVars start clean and reset after each test."""

    # Detect leakage from prior tests before forcing a clean baseline.
    assert request_id_context.get() == ""
    assert log_to_file_context.get() is False

    request_token = request_id_context.set("")
    log_token = log_to_file_context.set(False)

    try:
        yield
    finally:
        request_id_context.reset(request_token)
        log_to_file_context.reset(log_token)


@pytest.fixture
def temp_logs_dir():
    """Create a temporary directory for test logs."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def agency_factory():
    """Create an agency factory for testing."""

    def create_agency(load_threads_callback=None):
        agent = Agent(
            name="LogTestAgent",
            instructions="You are a test agent for logging middleware testing.",
            model_settings=ModelSettings(temperature=0),
        )
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
        )

    return create_agency


class TestConsoleFormatter:
    """Test console log formatting with request tracking."""

    def test_format_with_request_id(self):
        """Test that console formatter includes request ID when present."""
        formatter = ConsoleFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py", lineno=42, msg="Test message", args=(), exc_info=None
        )
        record.funcName = "test_func"
        record.module = "test_module"

        # Set request ID in context
        with set_context(request_id_context, "req-123"):
            formatted = formatter.format(record)

        assert "[req-123]" in formatted
        assert "[INFO]" in formatted
        assert "test_module.test_func:42" in formatted
        assert "Test message" in formatted

    def test_format_without_request_id(self):
        """Test console formatting when no request ID is set."""
        formatter = ConsoleFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="test.py",
            lineno=10,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        record.filename = "test.py"
        record.funcName = "test_function"
        record.module = "test_module"

        # Clear request ID context
        with set_context(request_id_context, ""):
            formatted = formatter.format(record)

        assert "[req-" not in formatted  # No request ID prefix
        assert "[WARNING]" in formatted
        assert "test_module.test_function:10" in formatted
        assert "Warning message" in formatted

    def test_format_with_exception(self):
        """Test console formatting includes exception details."""
        formatter = ConsoleFormatter()

        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=20,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        formatted = formatter.format(record)

        assert "Error occurred" in formatted
        assert "ValueError: Test exception" in formatted
        assert "Traceback" in formatted


class TestFileFormatter:
    """Test JSON file log formatting."""

    def test_format_basic_log(self):
        """Test JSON formatting for basic log entries."""
        formatter = FileFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=100,
            msg="JSON test message",
            args=(),
            exc_info=None,
        )
        record.funcName = "json_func"
        record.filename = "test.py"

        formatted = formatter.format(record)
        log_entry = json.loads(formatted)

        assert log_entry["message"] == "JSON test message"
        assert log_entry["details"]["level"] == "INFO"
        assert log_entry["details"]["location"]["file"] == "test.py"
        assert log_entry["details"]["location"]["function"] == "json_func"
        assert log_entry["details"]["location"]["line"] == 100
        assert "timestamp" in log_entry["details"]

    def test_format_with_exception_info(self):
        """Test JSON formatting includes structured exception data."""
        formatter = FileFormatter()

        try:
            raise RuntimeError("JSON test exception")
        except RuntimeError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=50,
            msg="Exception in JSON",
            args=(),
            exc_info=exc_info,
        )

        formatted = formatter.format(record)
        log_entry = json.loads(formatted)

        assert "exception" in log_entry["details"]
        assert log_entry["details"]["exception"]["type"] == "RuntimeError"
        assert log_entry["details"]["exception"]["message"] == "JSON test exception"
        assert isinstance(log_entry["details"]["exception"]["traceback"], list)


class TestConditionalFileHandler:
    """Test conditional file logging based on context."""

    def test_logs_when_enabled(self, temp_logs_dir):
        """Test that handler writes to file when context is enabled."""
        handler = ConditionalFileHandler(temp_logs_dir)
        handler.setFormatter(FileFormatter())

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Should be logged",
            args=(),
            exc_info=None,
        )

        # Enable file logging and set request ID
        with set_context(log_to_file_context, True), set_context(request_id_context, "test-id-123"):
            handler.emit(record)

        # Check that log file was created
        log_file = Path(temp_logs_dir) / "test-id-123.jsonl"
        assert log_file.exists()

        # Verify content
        content = log_file.read_text(encoding="utf-8")
        log_entry = json.loads(content.strip())
        assert log_entry["message"] == "Should be logged"

    def test_skips_when_disabled(self, temp_logs_dir):
        """Test that handler doesn't write when file logging is disabled."""
        handler = ConditionalFileHandler(temp_logs_dir)
        handler.setFormatter(FileFormatter())

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Should not be logged",
            args=(),
            exc_info=None,
        )

        # Disable file logging
        with set_context(log_to_file_context, False), set_context(request_id_context, "test-id-456"):
            handler.emit(record)

        # Check that no log file was created
        log_file = Path(temp_logs_dir) / "test-id-456.jsonl"
        assert not log_file.exists()

    def test_handles_write_errors_gracefully(self, temp_logs_dir):
        """Test that handler doesn't crash when file writing fails."""
        handler = ConditionalFileHandler(temp_logs_dir)
        handler.setFormatter(FileFormatter())

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="This should fail silently",
            args=(),
            exc_info=None,
        )

        with set_context(log_to_file_context, True), set_context(request_id_context, "error-test"):
            # Should not raise exception
            with patch("builtins.open", side_effect=OSError("write error")):
                handler.emit(record)


class TestSetupEnhancedLogging:
    """Test the logging setup function."""

    def test_creates_logs_directory(self, temp_logs_dir):
        """Test that setup creates the logs directory."""
        non_existent_dir = os.path.join(temp_logs_dir, "new_logs")
        assert not os.path.exists(non_existent_dir)

        logger = setup_enhanced_logging(non_existent_dir)

        assert os.path.exists(non_existent_dir)
        assert isinstance(logger, logging.Logger)

    def test_configures_handlers_correctly(self, temp_logs_dir):
        """Test that setup configures console and file handlers."""
        logger = setup_enhanced_logging(temp_logs_dir)

        # Should have exactly 2 handlers
        assert len(logger.handlers) == 2

        # Check handler names and types
        handler_names = [h.name for h in logger.handlers]
        assert "custom_console" in handler_names
        assert "custom_file" in handler_names

        # Check formatters
        console_handler = next(h for h in logger.handlers if h.name == "custom_console")
        file_handler = next(h for h in logger.handlers if h.name == "custom_file")

        assert isinstance(console_handler.formatter, ConsoleFormatter)
        assert isinstance(file_handler.formatter, FileFormatter)


class TestGetLogIdFromHeaders:
    """Test request header processing for log IDs."""

    def test_extracts_existing_log_id(self):
        """Test that function extracts log ID from headers when present."""
        mock_request = MagicMock()
        mock_request.headers.get.return_value = "custom-log-id-789"

        log_id, should_log = get_log_id_from_headers(mock_request)

        assert log_id == "custom-log-id-789"
        assert should_log is True

    def test_generates_new_log_id(self):
        """Test that function generates new log ID when header is missing."""
        mock_request = MagicMock()
        mock_request.headers.get.return_value = None

        log_id, should_log = get_log_id_from_headers(mock_request)

        assert len(log_id) == 8  # Should be 8-character UUID prefix
        assert should_log is False


class TestRequestTracker:
    """Test the HTTP middleware for request tracking."""

    @pytest.mark.asyncio
    async def test_sets_context_variables(self):
        """Test that middleware sets request ID and logging context."""
        middleware = RequestTracker(MagicMock())

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "middleware-test-id"

        async def mock_call_next(request):
            # Verify context is set during request processing
            assert request_id_context.get() == "middleware-test-id"
            assert log_to_file_context.get() is True
            return MagicMock()

        await middleware.dispatch(mock_request, mock_call_next)

        # Context variables should be reset after the request completes
        assert request_id_context.get() == ""
        assert log_to_file_context.get() is False

    @pytest.mark.asyncio
    async def test_resets_context_on_exception(self):
        """Middleware must reset context when downstream handlers fail."""

        middleware = RequestTracker(MagicMock())

        mock_request = MagicMock()
        mock_request.headers.get.return_value = "middleware-error-test"

        async def mock_call_next(request):
            assert request_id_context.get() == "middleware-error-test"
            assert log_to_file_context.get() is True
            raise RuntimeError("downstream failure")

        with pytest.raises(RuntimeError):
            await middleware.dispatch(mock_request, mock_call_next)

        assert request_id_context.get() == ""
        assert log_to_file_context.get() is False

    @pytest.mark.asyncio
    async def test_run_fastapi_logging_integration(self, agency_factory, temp_logs_dir):
        """Test logging middleware with actual run_fastapi method."""

        set_tracing_disabled(True)

        # Build FastAPI app with logging enabled
        app = run_fastapi(
            agencies={"test_agency": agency_factory},
            port=8099,
            logs_dir=temp_logs_dir,
            return_app=True,
            enable_agui=False,
            enable_logging=True,  # Enable logging to test the middleware
        )

        transport = httpx.ASGITransport(app=app)
        try:
            # Make request with log ID header against in-process app
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/test_agency/get_response",
                    json={"message": "Test logging middleware"},
                    headers={"x-agency-log-id": "fastapi-integration-test"},
                    timeout=30.0,
                )

            assert response.status_code == 200

            # Wait for log file to be written
            log_file = Path(temp_logs_dir) / "fastapi-integration-test.jsonl"
            for _ in range(20):
                if log_file.exists():
                    break
                await asyncio.sleep(0.1)

            assert log_file.exists()

            # Verify log content
            content = log_file.read_text(encoding="utf-8")
            log_lines = [line for line in content.strip().split("\n") if line.strip()]
            assert len(log_lines) >= 1  # Should have at least some logs

            # Parse and verify log entries
            for line in log_lines:
                log_entry = json.loads(line)
                assert "message" in log_entry
                assert "details" in log_entry
                assert "timestamp" in log_entry["details"]
        finally:
            await transport.aclose()


class TestGetLogsEndpointImpl:
    """Test the logs retrieval endpoint implementation."""

    @pytest.mark.asyncio
    async def test_retrieves_and_deletes_log_file(self, temp_logs_dir):
        """Test that endpoint returns logs and deletes the file."""
        # Create a test log file
        log_file = Path(temp_logs_dir) / "endpoint-test.jsonl"
        test_logs = [
            {"message": "Log entry 1", "details": {"level": "INFO"}},
            {"message": "Log entry 2", "details": {"level": "ERROR"}},
        ]

        with log_file.open("w", encoding="utf-8") as f:
            for log_entry in test_logs:
                f.write(json.dumps(log_entry) + "\n")

        # Call the endpoint
        response = await get_logs_endpoint_impl("endpoint-test", temp_logs_dir)

        assert response.status_code == 200
        assert response.media_type == "application/json"

        # Parse response content
        response_data = json.loads(response.body)
        assert len(response_data) == 2
        assert response_data[0]["message"] == "Log entry 1"
        assert response_data[1]["message"] == "Log entry 2"

        # Verify file was deleted
        assert not log_file.exists()

    @pytest.mark.asyncio
    async def test_returns_404_for_missing_file(self, temp_logs_dir):
        """Test that endpoint returns 404 for non-existent log files."""
        response = await get_logs_endpoint_impl("non-existent", temp_logs_dir)

        assert response.status_code == 404
        assert "Log file not found" in response.body.decode()

    @pytest.mark.asyncio
    async def test_returns_400_for_empty_log_id(self, temp_logs_dir):
        """Test that endpoint returns 400 for empty log ID."""
        response = await get_logs_endpoint_impl("", temp_logs_dir)

        assert response.status_code == 400
        assert "Log ID is required" in response.body.decode()

    @pytest.mark.asyncio
    async def test_handles_invalid_json_gracefully(self, temp_logs_dir):
        """Test that endpoint skips invalid JSON lines."""
        log_file = Path(temp_logs_dir) / "invalid-json-test.jsonl"

        with log_file.open("w", encoding="utf-8") as f:
            f.write('{"valid": "json"}\n')
            f.write("invalid json line\n")
            f.write('{"another": "valid"}\n')

        response = await get_logs_endpoint_impl("invalid-json-test", temp_logs_dir)

        assert response.status_code == 200
        response_data = json.loads(response.body)
        assert len(response_data) == 2  # Only valid JSON entries
        assert response_data[0]["valid"] == "json"
        assert response_data[1]["another"] == "valid"

    @pytest.mark.asyncio
    async def test_handles_file_system_errors(self):
        """Test that endpoint handles file system errors gracefully."""
        # Use invalid directory to trigger file system error
        with patch("os.path.exists", side_effect=OSError("File system error")):
            response = await get_logs_endpoint_impl("test-id", "/invalid/path")

            assert response.status_code == 500
            assert "Internal server error" in response.body.decode()
