"""Shared helpers for user-scoped OAuth persistence keys."""

import hashlib
import re


def build_oauth_user_segment(user_id: str, *, max_prefix_length: int = 96) -> str:
    """Return a stable, collision-resistant filesystem-safe user segment."""
    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", user_id).strip("._")
    if sanitized == "":
        sanitized = "default"
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16]
    return f"{sanitized[:max_prefix_length]}-{digest}"
