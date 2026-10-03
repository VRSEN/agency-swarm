"""File replacements must survive failed uploads without deleting the old copy."""

import os
from pathlib import Path

import httpx2
import pytest
from agents.exceptions import AgentsException
from openai import OpenAI

from agency_swarm import Agent


@pytest.mark.parametrize("outcome", ["upload_failure", "replacement", "unchanged"])
def test_replacement_upload_preserves_old_file_until_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    old_id = "file-123456789012345"
    new_id = "file-987654321098765"
    stored_files = {old_id}
    operations: list[str] = []

    def file_data(file_id: str) -> dict[str, object]:
        return {
            "id": file_id,
            "object": "file",
            "bytes": 4,
            "created_at": 100 if file_id == old_id else 300,
            "filename": "report.txt",
            "purpose": "assistants",
            "status": "processed",
        }

    def handle(request: httpx2.Request) -> httpx2.Response:
        if request.method == "GET":
            file_id = request.url.path.rsplit("/", 1)[-1]
            if file_id in stored_files:
                return httpx2.Response(200, json=file_data(file_id))
            return httpx2.Response(404, json={"error": {"message": "File not found"}})
        if request.method == "POST":
            operations.append("upload")
            if outcome == "upload_failure":
                return httpx2.Response(503, json={"error": {"message": "Upload unavailable"}})
            stored_files.add(new_id)
            return httpx2.Response(200, json=file_data(new_id))
        assert request.method == "DELETE"
        assert request.url.path.endswith(old_id)
        operations.append("delete")
        stored_files.remove(old_id)
        return httpx2.Response(200, json={"id": old_id, "object": "file", "deleted": True})

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    agent = Agent(name="FileReplacement")
    agent.files_folder_path = tmp_path
    assert agent.file_manager is not None
    local_file = tmp_path / f"report_{old_id}.txt"
    local_file.write_text("data", encoding="utf-8")
    timestamp = 100 if outcome == "unchanged" else 200
    os.utime(local_file, (timestamp, timestamp))

    with OpenAI(
        api_key="test-key", max_retries=0, http_client=httpx2.Client(transport=httpx2.MockTransport(handle))
    ) as client:
        agent._openai_client_sync = client
        if outcome == "upload_failure":
            with pytest.raises(AgentsException, match="Failed to upload"):
                agent.file_manager.upload_file(str(local_file))
            assert stored_files == {old_id}
            assert operations == ["upload"]
            assert local_file.read_text(encoding="utf-8") == "data"
        elif outcome == "replacement":
            assert agent.file_manager.upload_file(str(local_file)) == new_id
            assert operations == ["upload", "delete"]
            assert stored_files == {new_id}
            assert (tmp_path / f"report_{new_id}.txt").read_text(encoding="utf-8") == "data"
        else:
            assert agent.file_manager.upload_file(str(local_file)) == old_id
            assert operations == []
            assert stored_files == {old_id}
