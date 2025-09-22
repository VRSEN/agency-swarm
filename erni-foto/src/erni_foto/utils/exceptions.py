"""
Custom exceptions for Erni-Foto system.
"""

from typing import Any


class ErniFotoError(Exception):
    """Base exception for Erni-Foto system."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class SharePointError(ErniFotoError):
    """SharePoint-related errors."""

    def __init__(self, message: str, status_code: int | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.status_code = status_code


class OpenAIError(ErniFotoError):
    """OpenAI API-related errors."""

    def __init__(self, message: str, error_code: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.error_code = error_code


class ProcessingError(ErniFotoError):
    """Photo processing-related errors."""

    def __init__(self, message: str, file_path: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.file_path = file_path


class ConfigurationError(ErniFotoError):
    """Configuration-related errors."""

    pass


class ValidationError(ErniFotoError):
    """Data validation errors."""

    def __init__(self, message: str, field: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.field = field


class AuthenticationError(ErniFotoError):
    """Authentication-related errors."""

    pass


class NetworkError(ErniFotoError):
    """Network-related errors."""

    def __init__(self, message: str, url: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.url = url


class FileSystemError(ErniFotoError):
    """File system-related errors."""

    def __init__(self, message: str, path: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.path = path


class MetadataError(ErniFotoError):
    """Metadata-related errors."""

    def __init__(self, message: str, field_name: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.field_name = field_name


class BatchProcessingError(ErniFotoError):
    """Batch processing-related errors."""

    def __init__(self, message: str, batch_id: str | None = None, failed_items: list | None = None):
        super().__init__(message)
        self.batch_id = batch_id
        self.failed_items = failed_items or []


class RateLimitError(ErniFotoError):
    """Rate limiting errors."""

    def __init__(self, message: str, retry_after: int | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.retry_after = retry_after


class QuotaExceededError(ErniFotoError):
    """Quota exceeded errors."""

    def __init__(self, message: str, quota_type: str | None = None, details: dict[str, Any] | None = None):
        super().__init__(message, details)
        self.quota_type = quota_type
