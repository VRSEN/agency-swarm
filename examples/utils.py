import json
import shutil
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_GREEN = "\033[32m"
_RESET = "\033[0m"


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
        content = _extract_text(m.get("content") or m.get("output") or m.get("arguments"))
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


def iter_agent_messages(agency, *, agent_name: str | None = None) -> Iterator[dict[str, Any]]:
    """Yield stored messages filtered by optional caller/agent name."""
    for message in agency.thread_manager.get_all_messages():
        if not isinstance(message, dict):
            continue
        if agent_name and not (message.get("callerAgent") == agent_name or message.get("agent") == agent_name):
            continue
        yield message


def iter_send_message_calls(agency, *, agent_name: str | None = None) -> Iterator[dict[str, Any]]:
    """Yield send_message function call records matching optional agent filter."""
    for message in iter_agent_messages(agency, agent_name=agent_name):
        if message.get("type") == "function_call" and str(message.get("name", "")).startswith("send_message"):
            yield message


def format_json_call(arguments: str | dict[str, Any]) -> str:
    """Return pretty JSON from arguments string/dict."""
    if isinstance(arguments, str):
        parsed = json.loads(arguments or "{}")
    else:
        parsed = arguments
    return json.dumps(parsed, indent=2)


def print_highlighted_send_message_args(agency, *, agent_name: str | None = None) -> None:
    """Pretty-print send_message call arguments with highlighted keys."""
    for message in iter_send_message_calls(agency, agent_name=agent_name):
        rendered = format_json_call(message.get("arguments", {}))
        rendered = rendered.replace('"key_moments"', f'{_GREEN}"key_moments"{_RESET}').replace(
            '"decisions"', f'{_GREEN}"decisions"{_RESET}'
        )
        print(rendered)


def print_send_message_exchange(agency, *, owner: str) -> None:
    """Print send_message requests/responses involving a specific agent."""
    call_ids: dict[str, dict[str, Any]] = {}
    for message in iter_agent_messages(agency, agent_name=owner):
        if message.get("type") == "function_call" and str(message.get("name", "")).startswith("send_message"):
            call_ids[str(message.get("parent_run_id"))] = message
            payload = format_json_call(message.get("arguments", {}))
            print(f"Request {message.get('callerAgent')} -> {message.get('agent')}:\n{payload}\n")
        elif message.get("type") == "assistant" and str(message.get("parent_run_id")) in call_ids:
            response_text = _extract_text(message.get("content") or message.get("output"))
            print(f"Response {message.get('agent')} -> {message.get('callerAgent')}: {response_text}\n")
