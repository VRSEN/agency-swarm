"""Shared helpers for user-scoped OAuth persistence keys."""

import hashlib
import re


def build_oauth_cache_segment(
    value: str,
    *,
    max_prefix_length: int = 96,
    preserve_safe: bool = False,
) -> str:
    """Return a stable, collision-resistant filesystem-safe cache segment."""
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", value).strip("._")
    if sanitized == "":
        sanitized = "default"
    if preserve_safe and sanitized == value and len(value) <= max_prefix_length:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{sanitized[:max_prefix_length]}-{digest}"


def build_oauth_user_segment(user_id: str, *, max_prefix_length: int = 96) -> str:
    """Return a stable, collision-resistant filesystem-safe user segment."""
    return build_oauth_cache_segment(user_id, max_prefix_length=max_prefix_length)
