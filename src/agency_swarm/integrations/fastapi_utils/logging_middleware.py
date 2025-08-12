import json
import logging
import os
import traceback
import uuid
from contextvars import ContextVar
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Context variables for request tracking
request_id_context: ContextVar[str] = ContextVar("request_id", default="")
log_to_file_context: ContextVar[bool] = ContextVar("log_to_file", default=False)


class ConsoleFormatter(logging.Formatter):
    """Custom console formatter that includes request ID and enhanced location info."""

    def format(self, record):
        request_id = request_id_context.get("")
        if request_id:
            request_id_str = f"[{request_id}] "
        else:
            request_id_str = ""

        if hasattr(record, "funcName") and hasattr(record, "module"):
            location = f"{record.module}.{record.funcName}:{record.lineno}"
        elif hasattr(record, "filename"):
            location = f"{record.filename}:{record.lineno}"
        else:
            location = "unknown"

        formatted = f"{request_id_str}[{record.levelname}] {location} - {record.getMessage()}"

        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)
        elif record.levelno >= logging.ERROR:
            current_traceback = traceback.format_stack()
            if len(current_traceback) > 1:
                formatted += "\n" + "-" * 40 + " CALL STACK " + "-" * 40 + "\n" + "".join(current_traceback[:-1])

        return formatted


class FileFormatter(logging.Formatter):
    """JSON formatter for file logging with structured data."""

    def format(self, record):
        log_entry = {
            "message": record.getMessage(),
            "details": {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "location": {
                    "file": getattr(record, "filename", "unknown"),
                    "function": getattr(record, "funcName", "unknown"),
                    "line": getattr(record, "lineno", 0),
                },
            },
        }

        if record.exc_info:
            log_entry["details"]["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info).split("\n"),
            }
        elif record.levelno >= logging.ERROR:
            current_traceback = traceback.format_stack()
            if len(current_traceback) > 1:
                log_entry["details"]["call_stack"] = [line.strip() for line in current_traceback[:-1] if line.strip()]

        return json.dumps(log_entry, ensure_ascii=False)


class ConditionalFileHandler(logging.Handler):
    """Handler that only logs to file when enabled via context variable."""

    def __init__(self, logs_dir: str):
        super().__init__()
        self.logs_dir = logs_dir
        os.makedirs(logs_dir, exist_ok=True)

    def emit(self, record):
        if log_to_file_context.get(False):
            request_id = request_id_context.get("")
            if request_id:
                try:
                    log_file = os.path.join(self.logs_dir, f"{request_id}.jsonl")
                    formatted_message = self.format(record)

                    with open(log_file, "a", encoding="utf-8") as f:
                        f.write(formatted_message + "\n")
                except Exception:
                    pass


def setup_enhanced_logging(logs_dir: str = "activity-logs"):
    """Setup custom logging configuration with request tracking."""

    # Create logs directory
    os.makedirs(logs_dir, exist_ok=True)

    # Clear existing handlers
    logger = logging.getLogger()
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ConsoleFormatter())
    console_handler.name = "custom_console"

    # File handler
    file_handler = ConditionalFileHandler(logs_dir)
    file_handler.setFormatter(FileFormatter())
    file_handler.name = "custom_file"

    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    return logger


def get_log_id_from_headers(request: Request) -> tuple[str, bool]:
    """Extract log ID from request headers or generate a new one."""
    log_id = request.headers.get("x-agency-log-id")

    if log_id:
        return log_id, True

    return str(uuid.uuid4())[:8], False


class RequestTracker(BaseHTTPMiddleware):
    """Middleware that tracks requests and enables conditional file logging."""

    async def dispatch(self, request: Request, call_next):
        request_id, should_log_to_file = get_log_id_from_headers(request)
        request_id_context.set(request_id)
        log_to_file_context.set(should_log_to_file)

        response = await call_next(request)

        return response


async def get_logs_endpoint_impl(log_id: str, logs_dir: str = "activity-logs"):
    """Implementation to retrieve and delete log files."""
    try:
        if not log_id:
            return Response(
                status_code=400,
                content='{"error": "Log ID is required"}',
                media_type="application/json",
            )

        log_file = os.path.join(logs_dir, f"{log_id}.jsonl")

        if not os.path.exists(log_file):
            return Response(
                status_code=404,
                content='{"error": "Log file not found"}',
                media_type="application/json",
            )

        log_entries = []
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        log_entry = json.loads(line)
                        log_entries.append(log_entry)
                    except json.JSONDecodeError:
                        pass

        # Remove the log file after reading
        os.remove(log_file)

        # Return JSON format (same as original script)
        return Response(
            status_code=200,
            content=json.dumps(log_entries, ensure_ascii=False, indent=2),
            media_type="application/json",
        )

    except Exception:
        return Response(
            status_code=500,
            content='{"error": "Internal server error"}',
            media_type="application/json",
        )
