"""
Production logging and alerting system for Agency Swarm.

This module provides structured logging, error tracking, and alerting
capabilities for production deployments.
"""

import json
import logging
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class StructuredFormatter(logging.Formatter):
    """
    JSON formatter for structured logging in production.

    Outputs logs in JSON format for easy parsing by log aggregation systems
    like ELK stack, Fluentd, or cloud logging services.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""

        # Base log entry
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception information if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Add extra fields from the log record
        extra_fields = {}
        for key, value in record.__dict__.items():
            if key not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "getMessage",
                "exc_info",
                "exc_text",
                "stack_info",
                "message",
            }:
                extra_fields[key] = value

        if extra_fields:
            log_entry["extra"] = extra_fields

        return json.dumps(log_entry, default=str)


class ProductionLogger:
    """
    Production-ready logging system with structured output and alerting.
    """

    def __init__(
        self,
        log_level: str = "INFO",
        log_dir: str = "logs",
        enable_file_logging: bool = True,
        enable_console_logging: bool = True,
        max_log_files: int = 10,
        max_file_size_mb: int = 100,
    ):
        self.log_level = getattr(logging, log_level.upper())
        self.log_dir = Path(log_dir)
        self.enable_file_logging = enable_file_logging
        self.enable_console_logging = enable_console_logging
        self.max_log_files = max_log_files
        self.max_file_size_mb = max_file_size_mb

        # Create log directory
        if self.enable_file_logging:
            self.log_dir.mkdir(exist_ok=True)

        # Setup logging
        self._setup_logging()

        # Error tracking
        self.error_count = 0
        self.last_error_time: float | None = None
        self.error_threshold = 10  # Alert after 10 errors
        self.error_window_minutes = 5  # Within 5 minutes

    def _setup_logging(self) -> None:
        """Configure logging handlers and formatters."""

        # Get root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)

        # Clear existing handlers
        root_logger.handlers.clear()

        # Create structured formatter
        formatter = StructuredFormatter()

        # Console handler
        if self.enable_console_logging:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(self.log_level)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)

        # File handler
        if self.enable_file_logging:
            from logging.handlers import RotatingFileHandler

            log_file = self.log_dir / "agency_swarm.log"
            file_handler = RotatingFileHandler(
                log_file, maxBytes=self.max_file_size_mb * 1024 * 1024, backupCount=self.max_log_files
            )
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

        # Error file handler for critical errors
        if self.enable_file_logging:
            from logging.handlers import RotatingFileHandler

            error_log_file = self.log_dir / "errors.log"
            error_handler = RotatingFileHandler(
                error_log_file,
                maxBytes=50 * 1024 * 1024,  # 50MB
                backupCount=5,
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            root_logger.addHandler(error_handler)

    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        response_time_ms: float,
        user_agent: str | None = None,
        client_ip: str | None = None,
    ) -> None:
        """Log HTTP request with structured data."""

        logger = logging.getLogger("agency_swarm.requests")

        extra_data = {
            "request_method": method,
            "request_path": path,
            "response_status": status_code,
            "response_time_ms": round(response_time_ms, 2),
            "client_ip": client_ip,
            "user_agent": user_agent,
        }

        if status_code >= 500:
            logger.error(f"Server error: {method} {path} -> {status_code}", extra=extra_data)
            self._track_error()
        elif status_code >= 400:
            logger.warning(f"Client error: {method} {path} -> {status_code}", extra=extra_data)
        else:
            logger.info(f"Request: {method} {path} -> {status_code}", extra=extra_data)

    def log_agent_interaction(
        self,
        agent_name: str,
        message: str,
        response_time_ms: float,
        token_usage: dict[str, int] | None = None,
        error: str | None = None,
    ) -> None:
        """Log agent interaction with performance data."""

        logger = logging.getLogger("agency_swarm.agents")

        extra_data = {
            "agent_name": agent_name,
            "response_time_ms": round(response_time_ms, 2),
            "token_usage": token_usage,
            "message_length": len(message),
        }

        if error:
            extra_data["error"] = error
            logger.error(f"Agent error: {agent_name} - {error}", extra=extra_data)
            self._track_error()
        else:
            logger.info(f"Agent interaction: {agent_name}", extra=extra_data)

    def log_system_event(self, event_type: str, message: str, severity: str = "INFO", **kwargs: Any) -> None:
        """Log system events with custom data."""

        logger = logging.getLogger("agency_swarm.system")

        extra_data = {"event_type": event_type, **kwargs}

        level = getattr(logging, severity.upper(), logging.INFO)
        logger.log(level, message, extra=extra_data)

        if level >= logging.ERROR:
            self._track_error()

    def _track_error(self) -> None:
        """Track errors for alerting purposes."""
        current_time = time.time()

        # Reset counter if outside time window
        if self.last_error_time is None or current_time - self.last_error_time > self.error_window_minutes * 60:
            self.error_count = 0

        self.error_count += 1
        self.last_error_time = current_time

        # Check if we should send an alert
        if self.error_count >= self.error_threshold:
            self._send_alert(
                f"High error rate detected: {self.error_count} errors in {self.error_window_minutes} minutes"
            )
            # Reset counter after alert
            self.error_count = 0

    def _send_alert(self, message: str) -> None:
        """Send alert notification (placeholder for integration with alerting systems)."""

        alert_logger = logging.getLogger("agency_swarm.alerts")

        alert_data = {
            "alert_type": "error_threshold",
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "severity": "HIGH",
        }

        alert_logger.critical("ALERT: " + message, extra=alert_data)

        # TODO: Integrate with external alerting systems:
        # - Slack/Discord webhooks
        # - Email notifications
        # - PagerDuty/Opsgenie
        # - SMS alerts

        # Example webhook integration (commented out):
        # try:
        #     import requests
        #     webhook_url = os.getenv("ALERT_WEBHOOK_URL")
        #     if webhook_url:
        #         requests.post(webhook_url, json=alert_data, timeout=5)
        # except Exception as e:
        #     alert_logger.error(f"Failed to send webhook alert: {e}")

    def get_log_stats(self) -> dict[str, Any]:
        """Get logging statistics."""

        stats = {
            "error_count": self.error_count,
            "last_error_time": self.last_error_time,
            "log_level": logging.getLevelName(self.log_level),
            "file_logging_enabled": self.enable_file_logging,
            "console_logging_enabled": self.enable_console_logging,
        }

        # Add log file sizes if file logging is enabled
        if self.enable_file_logging and self.log_dir.exists():
            log_files = {}
            for log_file in self.log_dir.glob("*.log*"):
                try:
                    log_files[log_file.name] = {
                        "size_bytes": log_file.stat().st_size,
                        "modified": datetime.fromtimestamp(log_file.stat().st_mtime).isoformat(),
                    }
                except Exception:
                    pass
            stats["log_files"] = log_files

        return stats


# Global production logger instance
production_logger = None


def setup_production_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    enable_file_logging: bool = True,
    enable_console_logging: bool = True,
) -> ProductionLogger:
    """Setup production logging system."""

    global production_logger

    production_logger = ProductionLogger(
        log_level=log_level,
        log_dir=log_dir,
        enable_file_logging=enable_file_logging,
        enable_console_logging=enable_console_logging,
    )

    return production_logger


def get_production_logger() -> ProductionLogger | None:
    """Get the global production logger instance."""
    return production_logger
