from __future__ import annotations

from dataclasses import dataclass

import httpx
from openai import NotFoundError

from agency_swarm.agent.file_sync import FileSync


@dataclass(frozen=True)
class _VectorStoreFile:
    id: str


class _FakeFilesClient:
    def __init__(
        self,
        *,
        file_ids: set[str],
        operations: list[str],
        delete_error: Exception | None = None,
    ) -> None:
        self._file_ids = file_ids
        self._operations = operations
        self.delete_error = delete_error
        self._retrieve_existing_attempts: dict[str, int] = {}
        self.deleted_file_ids: list[str] = []
        self.retrieve_calls: list[str] = []

    def delete(self, *, file_id: str) -> None:
        self._operations.append(f"files.delete:{file_id}")
        if self.delete_error is not None:
            raise self.delete_error
        if file_id not in self._file_ids:
            raise NotFoundError(
                "not found",
                response=httpx.Response(404, request=httpx.Request("DELETE", "https://example.test")),
                body=None,
            )
        self.deleted_file_ids.append(file_id)
        self._retrieve_existing_attempts[file_id] = 2

    def retrieve(self, file_id: str) -> None:
        self.retrieve_calls.append(file_id)
        remaining_existing_attempts = self._retrieve_existing_attempts.get(file_id, 0)
        if remaining_existing_attempts > 0:
            self._retrieve_existing_attempts[file_id] = remaining_existing_attempts - 1
            return None
        self._file_ids.discard(file_id)
        raise NotFoundError(
            "not found",
            response=httpx.Response(404, request=httpx.Request("GET", "https://example.test")),
            body=None,
        )


class _FakeVectorStoreFilesClient:
    def __init__(
        self,
        *,
        attached_file_ids: set[str],
        operations: list[str],
        detach_error: Exception | None = None,
    ) -> None:
        self._attached_file_ids = attached_file_ids
        self._operations = operations
        self.detach_error = detach_error
        self.detached_file_ids: list[str] = []
        self.retrieve_calls: list[tuple[str, str]] = []

    def delete(self, *, vector_store_id: str, file_id: str) -> None:
        self._operations.append(f"vector_stores.files.delete:{vector_store_id}:{file_id}")
        if self.detach_error is not None:
            raise self.detach_error
        self._attached_file_ids.discard(file_id)
        self.detached_file_ids.append(file_id)

    def retrieve(self, *, vector_store_id: str, file_id: str) -> None:
        self.retrieve_calls.append((vector_store_id, file_id))
        if file_id not in self._attached_file_ids:
            raise NotFoundError(
                "not found",
                response=httpx.Response(404, request=httpx.Request("GET", "https://example.test")),
                body=None,
            )
        return None


class _FakeVectorStoresClient:
    def __init__(
        self,
        *,
        attached_file_ids: set[str],
        operations: list[str],
        detach_error: Exception | None = None,
    ) -> None:
        self.files = _FakeVectorStoreFilesClient(
            attached_file_ids=attached_file_ids,
            operations=operations,
            detach_error=detach_error,
        )


class _FakeClientSync:
    def __init__(
        self,
        *,
        attached_file_ids: set[str],
        file_ids: set[str],
        delete_error: Exception | None = None,
        detach_error: Exception | None = None,
    ) -> None:
        self.operations: list[str] = []
        self.files = _FakeFilesClient(file_ids=file_ids, operations=self.operations, delete_error=delete_error)
        self.vector_stores = _FakeVectorStoresClient(
            attached_file_ids=attached_file_ids,
            operations=self.operations,
            detach_error=detach_error,
        )


class _FakeAgent:
    def __init__(self, *, vs_id: str, client_sync: _FakeClientSync) -> None:
        self.name = "TestAgent"
        self._associated_vector_store_id = vs_id
        self.client_sync = client_sync
        self.files_folder_path = None
        self.file_manager = None


def test_sync_with_folder_deletes_orphan_before_detaching_vector_store_file() -> None:
    """Folder sync keeps the vector store attachment until the file object is deleted."""
    attached_file_ids = {"file-1"}
    file_ids = {"file-1"}
    client_sync = _FakeClientSync(attached_file_ids=attached_file_ids, file_ids=file_ids)
    agent = _FakeAgent(vs_id="vs_123", client_sync=client_sync)

    class _FileSyncFixedList(FileSync):
        def list_all_vector_store_files(self, vector_store_id: str) -> list[object]:
            assert vector_store_id == "vs_123"
            return [_VectorStoreFile(id="file-1")]

    sync = _FileSyncFixedList(agent)
    sync._sleep = lambda _: None
    sync.sync_with_folder()

    assert client_sync.vector_stores.files.detached_file_ids == ["file-1"]
    assert client_sync.files.deleted_file_ids == ["file-1"]
    assert client_sync.operations == [
        "files.delete:file-1",
        "vector_stores.files.delete:vs_123:file-1",
    ]
    assert client_sync.files.retrieve_calls == ["file-1", "file-1", "file-1"]
    assert attached_file_ids == set()
    assert file_ids == set()


def test_remove_file_from_vs_and_oai_detaches_before_deleting_openai_file() -> None:
    """`remove_file_from_vs_and_oai` should remove the attachment before deleting the file object."""
    attached_file_ids = {"file-1"}
    file_ids = {"file-1"}
    client_sync = _FakeClientSync(attached_file_ids=attached_file_ids, file_ids=file_ids)
    agent = _FakeAgent(vs_id="vs_123", client_sync=client_sync)

    sync = FileSync(agent)
    sync._sleep = lambda _: None
    sync.remove_file_from_vs_and_oai("file-1")

    assert client_sync.vector_stores.files.detached_file_ids == ["file-1"]
    assert client_sync.files.deleted_file_ids == ["file-1"]
    assert client_sync.operations == [
        "vector_stores.files.delete:vs_123:file-1",
        "files.delete:file-1",
    ]
    assert client_sync.files.retrieve_calls == ["file-1", "file-1", "file-1"]
    assert attached_file_ids == set()
    assert file_ids == set()


def test_remove_file_from_vs_and_oai_polls_vector_store_via_retrieve() -> None:
    """Removal waits should poll Vector Store via retrieve, not list."""
    attached_file_ids = {"file-1"}
    file_ids = {"file-1"}
    client_sync = _FakeClientSync(attached_file_ids=attached_file_ids, file_ids=file_ids)
    agent = _FakeAgent(vs_id="vs_123", client_sync=client_sync)

    class _FileSyncNoList(FileSync):
        def list_all_vector_store_files(self, vector_store_id: str) -> list[object]:
            raise AssertionError("list should not be used for absence polling")

    sync = _FileSyncNoList(agent)
    sync._sleep = lambda _: None
    sync.remove_file_from_vs_and_oai("file-1")

    assert client_sync.vector_stores.files.retrieve_calls == [
        ("vs_123", "file-1"),
        ("vs_123", "file-1"),
        ("vs_123", "file-1"),
    ]


def test_remove_file_from_vs_and_oai_keeps_file_when_detach_fails(caplog) -> None:
    """Detach failures should leave the OpenAI file for a later cleanup retry."""
    attached_file_ids = {"file-1"}
    file_ids = {"file-1"}
    client_sync = _FakeClientSync(
        attached_file_ids=attached_file_ids,
        file_ids=file_ids,
        detach_error=RuntimeError("temporary OpenAI failure"),
    )
    agent = _FakeAgent(vs_id="vs_123", client_sync=client_sync)

    sync = FileSync(agent)
    sync._sleep = lambda _: None
    sync.remove_file_from_vs_and_oai("file-1")

    assert client_sync.vector_stores.files.detached_file_ids == []
    assert client_sync.files.deleted_file_ids == []
    assert client_sync.files.retrieve_calls == []
    assert attached_file_ids == {"file-1"}
    assert file_ids == {"file-1"}
    assert "Failed to detach file file-1 from Vector Store vs_123" in caplog.text


def test_sync_with_folder_detach_failure_keeps_attachment_visible_for_later_retry() -> None:
    """A transient detach failure should keep the vector store attachment as the retry signal."""
    attached_file_ids = {"file-1"}
    file_ids = {"file-1"}
    client_sync = _FakeClientSync(
        attached_file_ids=attached_file_ids,
        file_ids=file_ids,
        detach_error=RuntimeError("temporary OpenAI failure"),
    )
    agent = _FakeAgent(vs_id="vs_123", client_sync=client_sync)

    class _FileSyncAttachedList(FileSync):
        def list_all_vector_store_files(self, vector_store_id: str) -> list[object]:
            assert vector_store_id == "vs_123"
            return [_VectorStoreFile(id=file_id) for file_id in sorted(attached_file_ids)]

    sync = _FileSyncAttachedList(agent)
    sync._sleep = lambda _: None

    sync.sync_with_folder()

    assert client_sync.vector_stores.files.detached_file_ids == []
    assert client_sync.files.deleted_file_ids == ["file-1"]
    assert attached_file_ids == {"file-1"}
    assert file_ids == set()

    client_sync.vector_stores.files.detach_error = None
    sync.sync_with_folder()

    assert client_sync.vector_stores.files.detached_file_ids == ["file-1"]
    assert client_sync.files.deleted_file_ids == ["file-1"]
    assert attached_file_ids == set()
    assert file_ids == set()


def test_sync_with_folder_delete_failure_keeps_orphan_visible_for_later_retry() -> None:
    """A transient file delete failure should keep the vector store attachment as the retry signal."""
    attached_file_ids = {"file-1"}
    file_ids = {"file-1"}
    client_sync = _FakeClientSync(
        attached_file_ids=attached_file_ids,
        file_ids=file_ids,
        delete_error=RuntimeError("temporary OpenAI failure"),
    )
    agent = _FakeAgent(vs_id="vs_123", client_sync=client_sync)

    class _FileSyncAttachedList(FileSync):
        def list_all_vector_store_files(self, vector_store_id: str) -> list[object]:
            assert vector_store_id == "vs_123"
            return [_VectorStoreFile(id=file_id) for file_id in sorted(attached_file_ids)]

    sync = _FileSyncAttachedList(agent)
    sync._sleep = lambda _: None

    sync.sync_with_folder()

    assert client_sync.vector_stores.files.detached_file_ids == []
    assert client_sync.files.deleted_file_ids == []
    assert attached_file_ids == {"file-1"}
    assert file_ids == {"file-1"}
    assert client_sync.operations == ["files.delete:file-1"]

    client_sync.files.delete_error = None
    sync.sync_with_folder()

    assert client_sync.vector_stores.files.detached_file_ids == ["file-1"]
    assert client_sync.files.deleted_file_ids == ["file-1"]
    assert attached_file_ids == set()
    assert file_ids == set()
    assert client_sync.operations == [
        "files.delete:file-1",
        "files.delete:file-1",
        "vector_stores.files.delete:vs_123:file-1",
    ]
