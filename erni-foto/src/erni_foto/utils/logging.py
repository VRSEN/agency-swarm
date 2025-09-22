"""
Logging utilities for Erni-Foto system.
"""

import logging
import logging.handlers
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from ..config import LoggingConfig


def setup_logging(config: LoggingConfig, log_dir: Path | None = None) -> None:
    """Setup logging configuration."""

    # Create log directory if specified
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.level.upper()))

    # Clear existing handlers
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(config.format)

    # Console handler with Rich formatting
    console_handler = RichHandler(
        console=Console(stderr=True),
        show_time=True,
        show_path=True,
        markup=True,
        rich_tracebacks=True,
    )
    console_handler.setLevel(getattr(logging, config.level.upper()))
    root_logger.addHandler(console_handler)

    # File handler for general logs
    if log_dir:
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "erni_foto.log",
            maxBytes=_parse_size(config.max_size),
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(getattr(logging, config.level.upper()))
        root_logger.addHandler(file_handler)

        # Error file handler
        error_handler = logging.handlers.RotatingFileHandler(
            log_dir / "erni_foto_errors.log",
            maxBytes=_parse_size(config.max_size),
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        root_logger.addHandler(error_handler)

        # Audit log handler if enabled
        if config.enable_audit_log:
            audit_handler = logging.handlers.TimedRotatingFileHandler(
                log_dir / "erni_foto_audit.log",
                when="midnight",
                interval=1,
                backupCount=config.audit_log_retention_days,
                encoding="utf-8",
            )
            audit_handler.setFormatter(formatter)
            audit_handler.setLevel(logging.INFO)

            # Create audit logger
            audit_logger = logging.getLogger("erni_foto.audit")
            audit_logger.addHandler(audit_handler)
            audit_logger.setLevel(logging.INFO)
            audit_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


def get_audit_logger() -> logging.Logger:
    """Get the audit logger instance."""
    return logging.getLogger("erni_foto.audit")


def _parse_size(size_str: str) -> int:
    """Parse size string to bytes."""
    size_str = size_str.upper().strip()

    if size_str.endswith("KB"):
        return int(size_str[:-2]) * 1024
    elif size_str.endswith("MB"):
        return int(size_str[:-2]) * 1024 * 1024
    elif size_str.endswith("GB"):
        return int(size_str[:-2]) * 1024 * 1024 * 1024
    else:
        # Assume bytes
        return int(size_str)


class LoggerMixin:
    """Mixin class to add logging capabilities."""

    @property
    def logger(self) -> logging.Logger:
        """Get logger for this class."""
        return get_logger(f"{self.__class__.__module__}.{self.__class__.__name__}")

    @property
    def audit_logger(self) -> logging.Logger:
        """Get audit logger."""
        return get_audit_logger()

    def log_audit(self, action: str, details: dict | None = None) -> None:
        """Log an audit event."""
        message = f"Action: {action}"
        if details:
            message += f" | Details: {details}"
        self.audit_logger.info(message)


class ContextLogger:
    """Context manager for logging with additional context."""

    def __init__(self, logger: logging.Logger, context: dict):
        self.logger = logger
        self.context = context
        self.old_factory = None

    def __enter__(self):
        self.old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record

        logging.setLogRecordFactory(record_factory)
        return self.logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.setLogRecordFactory(self.old_factory)
