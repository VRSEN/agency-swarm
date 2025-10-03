from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path


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
    for m in messages:
        if not isinstance(m, dict):
            continue
        role_obj = m.get("role") or m.get("type")
        role = str(role_obj) if role_obj is not None else ""
        if role and role not in roles:
            continue
        if role == "assistant":
            role = f"{m.get('agent')}:"
        elif role == "user" and m.get("callerAgent") is not None:
            role = f"{m.get('callerAgent')}:"
        content = _extract_text(m.get("content"))
        print(f"   [{role}] {content}")


@contextmanager
def temporary_files_folder(source_subdir: str = "data") -> Iterator[Path]:
    """Copy example files into a disposable `files` directory.

    The provided directory (relative to the examples folder) is copied into a
    temporary location where the folder is named exactly `files`. Vector store
    renaming can freely mutate that directory without touching the original
    assets. The temporary tree is removed on exit.
    """

    examples_dir = Path(__file__).parent
    source_dir = examples_dir / source_subdir

    if not source_dir.exists():
        raise FileNotFoundError(f"Example source directory not found: {source_dir}")

    temp_root = Path(tempfile.mkdtemp(prefix="agency-swarm-files-"))
    destination = temp_root / "files"

    shutil.copytree(source_dir, destination)

    try:
        yield destination
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
