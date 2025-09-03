from __future__ import annotations

from collections.abc import Iterable


def _extract_text(content: object) -> str:
    """Return human-readable text from message content.

    - If content is a list of dict parts with "text" keys, join them.
    - Else fall back to str(content).
    """
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(str(part.get("text")))
        if parts:
            return " ".join(parts)
    return str(content)


def print_history(thread_manager, roles: Iterable[str] = ("assistant", "system")) -> None:
    """Print a minimal, chronological history since the last user message.

    - Shows only role and content for roles in `roles` (default: assistant/system)
    """
    messages = thread_manager.get_all_messages()
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "user":
            last_user_idx = i
            break

    for m in messages[last_user_idx + 1 :]:
        if not isinstance(m, dict):
            continue
        role_obj = m.get("role") or m.get("type")
        role = str(role_obj) if role_obj is not None else ""
        if role and role not in roles:
            continue
        content = _extract_text(m.get("content"))
        print(f"   [{role}] {content}")
