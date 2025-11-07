"""Utility functions for voice_email_telegram agency."""


def validate_email(email: str) -> bool:
    """
    Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        True if valid email format, False otherwise
    """
    if not email or not isinstance(email, str):
        return False

    # RFC 5321: Email addresses cannot contain spaces
    if " " in email:
        return False

    # RFC 5321: Maximum email length is 254 characters
    if len(email) > 254:
        return False

    if "@" not in email:
        return False

    parts = email.split("@")
    if len(parts) != 2:
        return False

    local, domain = parts
    if not local or not domain:
        return False

    if "." not in domain:
        return False

    # Domain cannot start or end with a dot
    if domain.startswith(".") or domain.endswith("."):
        return False

    # Domain parts can only contain alphanumeric, hyphens, and dots
    # Check for invalid characters in domain
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-")
    if not all(c in allowed_chars for c in domain):
        return False

    return True


def truncate_text(text: str, max_length: int = 100) -> str:
    """
    Truncate text to maximum length with ellipsis.

    Args:
        text: Text to truncate
        max_length: Maximum length (default 100)

    Returns:
        Truncated text with ... if needed
    """
    # Handle non-string inputs
    if not isinstance(text, str):
        return ""

    if not text:
        return ""

    # Handle zero or negative max_length
    if max_length <= 0:
        return ""

    # Handle max_length < 3 - just return "..."
    if max_length < 3:
        return "..."

    if len(text) <= max_length:
        return text

    return text[:max_length - 3] + "..."
