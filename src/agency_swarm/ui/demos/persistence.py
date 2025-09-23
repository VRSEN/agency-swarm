import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

_CHATS_DIR: str | None = None


def set_chats_dir(path: str) -> None:
    global _CHATS_DIR
    _CHATS_DIR = str(path)


def get_chats_dir() -> str:
    base = _CHATS_DIR or os.environ.get("AGENCY_SWARM_CHATS_DIR") or str(Path.cwd() / ".agency_swarm_chats")
    Path(base).mkdir(parents=True, exist_ok=True)
    return base


def chat_file_path(chat_id: str) -> str:
    return str(Path(get_chats_dir()) / f"messages_{chat_id}.json")


def index_file_path() -> str:
    return str(Path(get_chats_dir()) / "index.json")


def load_index() -> dict[str, dict[str, Any]]:
    try:
        with open(index_file_path()) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_index(index: dict[str, dict[str, Any]]) -> None:
    with open(index_file_path(), "w") as f:
        json.dump(index, f, indent=2)


def summarize_messages(messages: list[dict[str, Any]]) -> str:
    def _clip(text: str, limit: int = 64) -> str:
        text = " ".join(text.split())
        return text if len(text) <= limit else text[: limit - 1] + "…"

    for msg in messages:
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            return _clip(msg["content"]) or "(no summary)"
    for msg in messages:
        if msg.get("role") == "assistant" and isinstance(msg.get("content"), str):
            return _clip(msg["content"]) or "(no summary)"
    for msg in messages:
        if msg.get("role") == "system" and isinstance(msg.get("content"), str):
            content = msg["content"]
            if "All user messages:" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if "All user messages:" in line and i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line.startswith("1."):
                            match = re.search(r'"([^"]+)"', next_line)
                            if match:
                                return _clip(match.group(1))
            quotes = re.findall(r'"([^"]+)"', content)
            if quotes:
                return _clip(quotes[0])
    return "(no summary)"


def format_relative(ts_iso: str | None) -> str:
    if not ts_iso:
        return "-"
    try:
        dt = datetime.fromisoformat(ts_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)  # noqa: UP017
        now = datetime.now(timezone.utc)  # noqa: UP017
        delta = now - dt
        s = int(delta.total_seconds())
        if s < 60:
            return f"{s}s ago"
        m = s // 60
        if m < 60:
            return f"{m}m ago"
        h = m // 60
        if h < 48:
            return f"{h}h ago"
        d = h // 24
        if d < 14:
            return f"{d} day ago" if d == 1 else f"{d} days ago"
        w = d // 7
        return f"{w} week ago" if w == 1 else f"{w} weeks ago"
    except Exception:
        return "-"


def update_index(chat_id: str, messages: list[dict[str, Any]], branch: str) -> None:
    index = load_index()
    now_iso = datetime.now(timezone.utc).isoformat()  # noqa: UP017
    summary = summarize_messages(messages)
    msgs_count = len(messages)

    existing = index.get(chat_id) or {}
    created_at = existing.get("created_at") or now_iso

    index[chat_id] = {
        "chat_id": chat_id,
        "created_at": created_at,
        "modified_at": now_iso,
        "msgs": msgs_count,
        "branch": branch,
        "summary": summary,
    }
    save_index(index)


def list_chat_records() -> list[dict[str, Any]]:
    idx = load_index()
    if idx:
        index_records = list(idx.values())
        index_records.sort(key=lambda r: (r.get("modified_at") or "", r.get("chat_id") or ""), reverse=True)
        return index_records

    # Fallback to scanning message files
    scan_records: list[dict[str, Any]] = []
    for p in Path(get_chats_dir()).glob("messages_*.json"):
        chat_id = p.stem.removeprefix("messages_")
        try:
            with open(p) as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                raw_items = payload.get("items")
                items = cast(list[dict[str, Any]], raw_items if isinstance(raw_items, list) else [])
                meta = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
                created = meta.get("created_at")
                modified = meta.get("modified_at")
                msgs = meta.get("msgs") if isinstance(meta.get("msgs"), int) else len(items)
                branch = meta.get("branch") or ""
                summary = summarize_messages(items)
            else:
                items = cast(list[dict[str, Any]], payload if isinstance(payload, list) else [])
                created = None
                modified = None
                msgs = len(items)
                branch = ""
                summary = summarize_messages(items)
            scan_records.append(
                {
                    "chat_id": chat_id,
                    "created_at": created,
                    "modified_at": modified,
                    "msgs": msgs,
                    "branch": branch,
                    "summary": summary,
                }
            )
        except Exception:
            continue
    scan_records.sort(key=lambda r: (r.get("modified_at") or "", r.get("chat_id") or ""), reverse=True)
    return scan_records


def save_current_chat(agency_instance: Any, chat_id: str) -> None:
    file_path = chat_file_path(chat_id)
    messages = agency_instance.thread_manager.get_all_messages()

    # Existing created_at
    created_at: str | None = None
    try:
        if os.path.exists(file_path):
            with open(file_path) as rf:
                existing = json.load(rf)
            if isinstance(existing, dict):
                created_at = existing.get("metadata", {}).get("created_at")
    except Exception:
        created_at = None

    # Branch (best-effort)
    try:
        branch = (
            subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:
        branch = ""

    now_iso = datetime.now(timezone.utc).isoformat()  # noqa: UP017
    meta = {
        "created_at": created_at or now_iso,
        "modified_at": now_iso,
        "msgs": len(messages),
        "branch": branch,
        "summary": summarize_messages(messages),
    }

    with open(file_path, "w") as f:
        json.dump({"items": messages, "metadata": meta}, f, indent=2)

    update_index(chat_id, messages, branch)


def _read_chat_messages(chat_id: str) -> list[dict[str, Any]]:
    path = Path(chat_file_path(chat_id))
    if not path.exists():
        return []

    with open(path) as f:
        payload = json.load(f)

    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return items
    elif isinstance(payload, list):
        return payload

    raise ValueError("Chat payload must be a list of messages.")


def load_chat(agency_instance: Any, chat_id: str) -> bool:
    """Load messages from disk for a given chat_id.

    Returns False if the chat file does not exist. Returns True after
    successfully loading (including the edge case of an existing file with
    zero messages).
    """
    path = Path(chat_file_path(chat_id))
    if not path.exists():
        return False
    try:
        messages = _read_chat_messages(chat_id)
    except Exception:
        return False

    agency_instance.thread_manager.replace_messages(messages)
    return True
