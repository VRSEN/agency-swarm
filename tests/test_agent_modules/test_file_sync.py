"""Unit tests for the FileSync helper."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from openai import NotFoundError

from agency_swarm.agent.file_sync import FileSync


class DummyAgent:
    def __init__(self, *, folder: Path | None = None) -> None:
        self.name = "SyncAgent"
        self.files_folder_path = folder
        self.file_manager = SimpleNamespace(get_id_from_file=lambda entry: entry.stem)
        self._associated_vector_store_id = "vs_123"
        self.client_sync = SimpleNamespace(
            vector_stores=SimpleNamespace(files=SimpleNamespace(delete=lambda **_: None, list=lambda **_: None)),
            files=SimpleNamespace(delete=lambda **_: None),
        )


def test_collect_local_file_ids_handles_errors(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Visible files are collected; hidden or failing entries are skipped."""
    (tmp_path / "visible.txt").write_text("data")
    (tmp_path / ".hidden.txt").write_text("data")
    (tmp_path / "__cache.log").write_text("data")
    (tmp_path / "error.txt").write_text("data")

    agent = DummyAgent(folder=tmp_path)

    def fake_get_id(entry: Path) -> str | None:
        if entry.name == "error.txt":
            raise ValueError("boom")
        return entry.stem if entry.name == "visible.txt" else None

    agent.file_manager.get_id_from_file = fake_get_id

    caplog.set_level(logging.DEBUG)
    syncer = FileSync(agent)

    ids = syncer.collect_local_file_ids()

    assert ids == {"visible"}
    assert "Skipping file id parse for error.txt" in caplog.text


def test_list_all_vector_store_files_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pagination should accumulate data until has_more becomes false."""
    agent = DummyAgent()
    pages = [
        SimpleNamespace(data=[SimpleNamespace(id="first")], has_more=True, last_id="cursor"),
        SimpleNamespace(data=[SimpleNamespace(id="second")], has_more=False, last_id=None),
    ]
    calls: list[str | None] = []

    def fake_list(*, vector_store_id: str, limit: int, after: str | None):
        calls.append(after)
        return pages[len(calls) - 1]

    agent.client_sync.vector_stores.files.list = fake_list
    syncer = FileSync(agent)

    results = syncer.list_all_vector_store_files("vs_123")

    assert [item.id for item in results] == ["first", "second"]
    assert calls == [None, "cursor"]


def test_sync_with_folder_removes_remote_orphans(monkeypatch: pytest.MonkeyPatch) -> None:
    """Files absent locally should be pruned from both vector store and OpenAI storage."""
    agent = DummyAgent()
    deleted_vs: list[tuple[str, str]] = []
    deleted_files: list[str] = []

    def fake_collect(self: FileSync) -> set[str]:
        return {"keep"}

    def fake_list(self: FileSync, vs_id: str):
        return [
            SimpleNamespace(file_id="keep"),
            SimpleNamespace(file_id=None, id="legacy"),
            SimpleNamespace(file_id="drop"),
        ]

    def fake_vs_delete(*, vector_store_id: str, file_id: str) -> None:
        deleted_vs.append((vector_store_id, file_id))

    def fake_file_delete(*, file_id: str) -> None:
        deleted_files.append(file_id)

    monkeypatch.setattr(FileSync, "collect_local_file_ids", fake_collect)
    monkeypatch.setattr(FileSync, "list_all_vector_store_files", fake_list)
    agent.client_sync.vector_stores.files.delete = fake_vs_delete
    agent.client_sync.files.delete = fake_file_delete

    FileSync(agent).sync_with_folder()

    assert deleted_vs == [("vs_123", "legacy"), ("vs_123", "drop")]
    assert deleted_files == ["legacy", "drop"]


def test_sync_with_folder_handles_missing_vector_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vector store lookup failures should be swallowed."""
    agent = DummyAgent()

    def fake_list(self: FileSync, vs_id: str):
        raise NotFoundError(
            message="missing",
            response=httpx.Response(404, request=httpx.Request("GET", "https://example.com")),
            body=None,
        )

    monkeypatch.setattr(FileSync, "list_all_vector_store_files", fake_list)

    FileSync(agent).sync_with_folder()  # Should not raise


def test_remove_file_from_vs_and_oai_handles_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deletion errors should be logged at debug level without propagation."""
    agent = DummyAgent()
    vs_calls: list[tuple[str, str]] = []
    file_calls: list[str] = []

    def fake_vs_delete(*, vector_store_id: str, file_id: str) -> None:
        vs_calls.append((vector_store_id, file_id))
        raise Exception("vs failure")

    def fake_file_delete(*, file_id: str) -> None:
        file_calls.append(file_id)
        raise Exception("file failure")

    agent.client_sync.vector_stores.files.delete = fake_vs_delete
    agent.client_sync.files.delete = fake_file_delete

    FileSync(agent).remove_file_from_vs_and_oai("drop")

    assert vs_calls == [("vs_123", "drop")]
    assert file_calls == ["drop"]
