import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from agency_swarm.ui.demos import persistence
from agency_swarm.ui.demos.launcher import TerminalDemoLauncher
from agency_swarm.utils.thread import ThreadManager


class _Agency:
    def __init__(self, messages: list[dict[str, str]]) -> None:
        self.thread_manager = ThreadManager()
        self.thread_manager.replace_messages(messages)


def test_persistence_roundtrip_exercises_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    persistence.set_chats_dir(str(tmp_path))

    # Stabilise branch detection inside save_current_chat.
    monkeypatch.setattr(
        persistence.subprocess,
        "check_output",
        lambda *_, **__: b"main\n",
    )

    user_msg = {"role": "user", "content": "call me maybe"}
    assistant_msg = {"role": "assistant", "content": "ok"}

    agency = _Agency([user_msg, assistant_msg])
    chat_id = "chat_coverage"

    persistence.save_current_chat(agency, chat_id)

    # Index and file should exist with non-trivial metadata.
    chat_file = Path(persistence.chat_file_path(chat_id))
    assert chat_file.exists()

    index_file = Path(persistence.index_file_path())
    assert index_file.exists()

    # Loading should honour replace_messages and return True even when files exist.
    fresh_agency = _Agency([])
    assert persistence.load_chat(fresh_agency, chat_id) is True
    assert fresh_agency.thread_manager.get_all_messages() == [user_msg, assistant_msg]

    # Helpers: summarise by user content and render relative timestamps without crashing.
    summary = persistence.summarize_messages([assistant_msg, user_msg])
    assert summary == "call me maybe"

    timestamp = datetime.now(UTC).isoformat()
    assert persistence.format_relative(timestamp).endswith("ago")

    # list_chat_records should surface the saved entry and include metadata counts.
    records = TerminalDemoLauncher.list_chat_records()
    assert records and records[0]["chat_id"] == chat_id
    assert records[0]["msgs"] == 2

    # Sanity check that raw payload matches expectations.
    payload = json.loads(chat_file.read_text())
    assert payload["metadata"]["summary"] == "call me maybe"
