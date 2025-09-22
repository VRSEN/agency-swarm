"""
Utility modules for Erni-Foto system.
"""

from .decorators import cache_result, handle_errors, log_execution_time, rate_limit, retry, validate_config
from .exceptions import (
    AuthenticationError,
    BatchProcessingError,
    ConfigurationError,
    ErniFotoError,
    FileSystemError,
    MetadataError,
    NetworkError,
    OpenAIError,
    ProcessingError,
    QuotaExceededError,
    RateLimitError,
    SharePointError,
    ValidationError,
)
from .hash_utils import (
    calculate_file_hash,
    calculate_image_hash,
    compare_image_hashes,
    find_duplicate_images,
    get_cached_file_hash,
)
from .image_utils import ImageProcessor
from .logging import ContextLogger, LoggerMixin, get_audit_logger, get_logger, setup_logging

__all__ = [
    # Logging
    "setup_logging",
    "get_logger",
    "ContextLogger",
    "LoggerMixin",
    "get_audit_logger",
    # Exceptions
    "ErniFotoError",
    "SharePointError",
    "OpenAIError",
    "ProcessingError",
    "AuthenticationError",
    "BatchProcessingError",
    "ConfigurationError",
    "FileSystemError",
    "MetadataError",
    "NetworkError",
    "QuotaExceededError",
    "RateLimitError",
    "ValidationError",
    # Decorators
    "retry",
    "log_execution_time",
    "handle_errors",
    "cache_result",
    "rate_limit",
    "validate_config",
    # Image processing
    "ImageProcessor",
    # Hash utilities
    "calculate_file_hash",
    "calculate_image_hash",
    "compare_image_hashes",
    "find_duplicate_images",
    "get_cached_file_hash",
]
