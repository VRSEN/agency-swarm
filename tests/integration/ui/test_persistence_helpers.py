import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

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


def test_summarize_messages_edge_cases() -> None:
    """Test summarize_messages with various message patterns."""

    # Test with assistant message first (fallback to assistant)
    messages = [
        {"role": "assistant", "content": "I can help you with that"},
        {"role": "system", "content": "System message"},
    ]
    assert persistence.summarize_messages(messages) == "I can help you with that"

    # Test with system message containing quoted text
    system_msg = {
        "role": "system",
        "content": 'All user messages:\n1. "Hello world" - user greeting\n2. Something else',
    }
    assert persistence.summarize_messages([system_msg]) == "Hello world"

    # Test with system message with quotes but no "All user messages:" pattern
    system_msg_quotes = {"role": "system", "content": 'Some instructions with "quoted text" and more content'}
    assert persistence.summarize_messages([system_msg_quotes]) == "quoted text"

    # Test with system message but no quoted content
    system_msg_no_quotes = {"role": "system", "content": "No quotes here at all"}
    assert persistence.summarize_messages([system_msg_no_quotes]) == "(no summary)"

    # Test with empty messages
    assert persistence.summarize_messages([]) == "(no summary)"

    # Test with non-string content
    messages_non_string = [{"role": "user", "content": None}, {"role": "assistant", "content": 123}]
    assert persistence.summarize_messages(messages_non_string) == "(no summary)"

    # Test clipping long text
    long_message = {"role": "user", "content": "x" * 100}
    summary = persistence.summarize_messages([long_message])
    assert len(summary) <= 64
    assert summary.endswith("…")


def test_format_relative_edge_cases() -> None:
    """Test format_relative with various timestamp scenarios."""

    # Test with None timestamp
    assert persistence.format_relative(None) == "-"

    # Test with empty string
    assert persistence.format_relative("") == "-"

    # Test with invalid timestamp format
    assert persistence.format_relative("invalid-timestamp") == "-"

    # Test with naive datetime (no timezone)
    now = datetime.now()
    naive_iso = now.isoformat()
    result = persistence.format_relative(naive_iso)
    assert result.endswith("ago")

    # Test various time intervals
    now_utc = datetime.now(UTC)

    # 30 seconds ago
    past_30s = now_utc.timestamp() - 30
    past_30s_dt = datetime.fromtimestamp(past_30s, UTC)
    assert "s ago" in persistence.format_relative(past_30s_dt.isoformat())

    # 30 minutes ago
    past_30m = now_utc.timestamp() - 30 * 60
    past_30m_dt = datetime.fromtimestamp(past_30m, UTC)
    assert "m ago" in persistence.format_relative(past_30m_dt.isoformat())

    # 12 hours ago
    past_12h = now_utc.timestamp() - 12 * 3600
    past_12h_dt = datetime.fromtimestamp(past_12h, UTC)
    assert "h ago" in persistence.format_relative(past_12h_dt.isoformat())

    # 3 days ago
    past_3d = now_utc.timestamp() - 3 * 24 * 3600
    past_3d_dt = datetime.fromtimestamp(past_3d, UTC)
    result = persistence.format_relative(past_3d_dt.isoformat())
    assert result == "3 days ago"

    # 10 days ago (plural)
    past_10d = now_utc.timestamp() - 10 * 24 * 3600
    past_10d_dt = datetime.fromtimestamp(past_10d, UTC)
    assert "days ago" in persistence.format_relative(past_10d_dt.isoformat())

    # 2 weeks ago
    past_2w = now_utc.timestamp() - 14 * 24 * 3600
    past_2w_dt = datetime.fromtimestamp(past_2w, UTC)
    result = persistence.format_relative(past_2w_dt.isoformat())
    assert "week" in result


def test_list_chat_records_fallback_scanning(tmp_path: Path) -> None:
    """Test list_chat_records fallback when no index exists."""
    persistence.set_chats_dir(str(tmp_path))

    # Create message files without an index
    chat1_path = tmp_path / "messages_chat1.json"
    chat2_path = tmp_path / "messages_chat2.json"

    # Chat1: New format with metadata
    chat1_data = {
        "items": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there"}],
        "metadata": {
            "created_at": "2024-01-01T12:00:00Z",
            "modified_at": "2024-01-01T12:05:00Z",
            "msgs": 2,
            "branch": "main",
            "summary": "Hello",
        },
    }
    with open(chat1_path, "w") as f:
        json.dump(chat1_data, f)

    # Chat2: Legacy format (just list of messages)
    chat2_data = [{"role": "user", "content": "Legacy message"}, {"role": "assistant", "content": "Legacy response"}]
    with open(chat2_path, "w") as f:
        json.dump(chat2_data, f)

    # Chat3: Invalid JSON format (should be skipped)
    chat3_path = tmp_path / "messages_chat3.json"
    with open(chat3_path, "w") as f:
        f.write("invalid json content")

    # Chat4: New format but with invalid metadata types
    chat4_path = tmp_path / "messages_chat4.json"
    chat4_data = {
        "items": [{"role": "user", "content": "Test"}],
        "metadata": "invalid_metadata_type",  # Should be dict
    }
    with open(chat4_path, "w") as f:
        json.dump(chat4_data, f)

    records = persistence.list_chat_records()

    # Should have 3 valid records (chat1, chat2, chat4)
    assert len(records) == 3

    # Find chat1 record
    chat1_record = next(r for r in records if r["chat_id"] == "chat1")
    assert chat1_record["created_at"] == "2024-01-01T12:00:00Z"
    assert chat1_record["modified_at"] == "2024-01-01T12:05:00Z"
    assert chat1_record["msgs"] == 2
    assert chat1_record["branch"] == "main"
    assert chat1_record["summary"] == "Hello"

    # Find chat2 record (legacy format)
    chat2_record = next(r for r in records if r["chat_id"] == "chat2")
    assert chat2_record["created_at"] is None
    assert chat2_record["modified_at"] is None
    assert chat2_record["msgs"] == 2
    assert chat2_record["branch"] == ""
    assert chat2_record["summary"] == "Legacy message"

    # Find chat4 record (invalid metadata)
    chat4_record = next(r for r in records if r["chat_id"] == "chat4")
    assert chat4_record["msgs"] == 1
    assert chat4_record["summary"] == "Test"


def test_save_current_chat_error_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test save_current_chat error handling scenarios."""
    persistence.set_chats_dir(str(tmp_path))

    # Test with existing file that has invalid JSON (should handle gracefully)
    chat_id = "error_test"
    file_path = persistence.chat_file_path(chat_id)

    # Create invalid JSON file
    with open(file_path, "w") as f:
        f.write("invalid json content")

    agency = _Agency([{"role": "user", "content": "Test message"}])

    # Mock subprocess to fail (git command not available)
    def mock_subprocess_error(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr(subprocess, "check_output", mock_subprocess_error)

    # Should not raise exception despite errors
    persistence.save_current_chat(agency, chat_id)

    # Verify file was created successfully
    assert Path(file_path).exists()

    # Verify content is valid JSON now
    with open(file_path) as f:
        data = json.load(f)

    assert "items" in data
    assert "metadata" in data
    assert data["metadata"]["branch"] == ""  # Should be empty due to git error


def test_load_chat_error_scenarios(tmp_path: Path) -> None:
    """Test load_chat error handling and edge cases."""
    persistence.set_chats_dir(str(tmp_path))

    agency = _Agency([])

    # Test loading non-existent chat
    assert persistence.load_chat(agency, "nonexistent") is False

    # Test loading chat with invalid JSON
    invalid_chat_id = "invalid_json"
    invalid_path = persistence.chat_file_path(invalid_chat_id)
    with open(invalid_path, "w") as f:
        f.write("invalid json content")

    assert persistence.load_chat(agency, invalid_chat_id) is False

    # Test loading chat with valid JSON but wrong structure
    wrong_structure_id = "wrong_structure"
    wrong_path = persistence.chat_file_path(wrong_structure_id)
    with open(wrong_path, "w") as f:
        json.dump({"wrong": "structure"}, f)

    # This should raise ValueError in _read_chat_messages
    assert persistence.load_chat(agency, wrong_structure_id) is False

    # Test loading empty chat (should return True)
    empty_chat_id = "empty_chat"
    empty_path = persistence.chat_file_path(empty_chat_id)
    with open(empty_path, "w") as f:
        json.dump({"items": [], "metadata": {}}, f)

    assert persistence.load_chat(agency, empty_chat_id) is True
    assert len(agency.thread_manager.get_all_messages()) == 0


def test_read_chat_messages_error_cases(tmp_path: Path) -> None:
    """Test _read_chat_messages with various error scenarios."""
    persistence.set_chats_dir(str(tmp_path))

    # Test with non-existent file
    messages = persistence._read_chat_messages("nonexistent")
    assert messages == []

    # Test with invalid payload structure
    invalid_id = "invalid_payload"
    invalid_path = persistence.chat_file_path(invalid_id)
    with open(invalid_path, "w") as f:
        json.dump("string_payload", f)  # Should be dict or list

    with pytest.raises(ValueError, match="Chat payload must be a list of messages"):
        persistence._read_chat_messages(invalid_id)


def test_get_chats_dir_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test get_chats_dir with environment variable."""
    # Reset global state
    persistence.set_chats_dir("")

    test_dir = "/tmp/test_chats"
    monkeypatch.setenv("AGENCY_SWARM_CHATS_DIR", test_dir)

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        result = persistence.get_chats_dir()
        assert result == test_dir
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_load_index_with_invalid_data(tmp_path: Path) -> None:
    """Test load_index with invalid JSON data."""
    persistence.set_chats_dir(str(tmp_path))

    # Create index file with non-dict data
    index_path = persistence.index_file_path()
    with open(index_path, "w") as f:
        json.dump(["not", "a", "dict"], f)

    # Should return empty dict for non-dict data
    index = persistence.load_index()
    assert index == {}

    # Test with invalid JSON
    with open(index_path, "w") as f:
        f.write("invalid json")

    index = persistence.load_index()
    assert index == {}
