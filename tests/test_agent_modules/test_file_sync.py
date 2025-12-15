from __future__ import annotations

from dataclasses import dataclass

import httpx
from openai import NotFoundError

from agency_swarm.agent.file_sync import FileSync


@dataclass(frozen=True)
class _VectorStoreFile:
    id: str


class _FakeFilesClient:
    def __init__(self, *, attached_file_ids: set[str]) -> None:
        self._attached_file_ids = attached_file_ids
        self.deleted_file_ids: list[str] = []

    def delete(self, *, file_id: str) -> None:
        self._attached_file_ids.discard(file_id)
        self.deleted_file_ids.append(file_id)

    def retrieve(self, file_id: str) -> None:  # pragma: no cover - not used in these tests
        raise NotFoundError(
            "not found",
            response=httpx.Response(404, request=httpx.Request("GET", "https://example.test")),
            body=None,
        )


class _FakeVectorStoreFilesClient:
    def __init__(self, *, attached_file_ids: set[str]) -> None:
        self._attached_file_ids = attached_file_ids
        self.detached_file_ids: list[str] = []
        self.retrieve_calls: list[tuple[str, str]] = []

    def delete(self, *, vector_store_id: str, file_id: str) -> None:
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
    def __init__(self, *, attached_file_ids: set[str]) -> None:
        self.files = _FakeVectorStoreFilesClient(attached_file_ids=attached_file_ids)


class _FakeClientSync:
    def __init__(self, *, attached_file_ids: set[str]) -> None:
        self.files = _FakeFilesClient(attached_file_ids=attached_file_ids)
        self.vector_stores = _FakeVectorStoresClient(attached_file_ids=attached_file_ids)


class _FakeAgent:
    def __init__(self, *, vs_id: str, client_sync: _FakeClientSync) -> None:
        self.name = "TestAgent"
        self._associated_vector_store_id = vs_id
        self.client_sync = client_sync
        self.files_folder_path = None
        self.file_manager = None


def test_sync_with_folder_file_delete_detaches_from_vector_store() -> None:
    """OpenAI file deletion should remove the file from all vector stores."""
    attached_file_ids = {"file-1"}
    client_sync = _FakeClientSync(attached_file_ids=attached_file_ids)
    agent = _FakeAgent(vs_id="vs_123", client_sync=client_sync)

    class _FileSyncFixedList(FileSync):
        def list_all_vector_store_files(self, vector_store_id: str) -> list[object]:
            assert vector_store_id == "vs_123"
            return [_VectorStoreFile(id="file-1")]

    sync = _FileSyncFixedList(agent)
    sync.sync_with_folder()

    assert client_sync.vector_stores.files.detached_file_ids == []
    assert client_sync.files.deleted_file_ids == ["file-1"]
    assert attached_file_ids == set()


def test_remove_file_from_vs_and_oai_relies_on_openai_delete_detachment() -> None:
    """`remove_file_from_vs_and_oai` should not need explicit Vector Store detachment."""
    attached_file_ids = {"file-1"}
    client_sync = _FakeClientSync(attached_file_ids=attached_file_ids)
    agent = _FakeAgent(vs_id="vs_123", client_sync=client_sync)

    sync = FileSync(agent)
    sync.remove_file_from_vs_and_oai("file-1")

    assert client_sync.vector_stores.files.detached_file_ids == []
    assert client_sync.files.deleted_file_ids == ["file-1"]
    assert attached_file_ids == set()


def test_remove_file_from_vs_and_oai_polls_vector_store_via_retrieve() -> None:
    """Removal waits should poll Vector Store via retrieve, not list."""
    attached_file_ids = {"file-1"}
    client_sync = _FakeClientSync(attached_file_ids=attached_file_ids)
    agent = _FakeAgent(vs_id="vs_123", client_sync=client_sync)

    class _FileSyncNoList(FileSync):
        def list_all_vector_store_files(self, vector_store_id: str) -> list[object]:
            raise AssertionError("list should not be used for absence polling")

    sync = _FileSyncNoList(agent)
    sync.remove_file_from_vs_and_oai("file-1")

    assert client_sync.vector_stores.files.retrieve_calls == [("vs_123", "file-1")]
