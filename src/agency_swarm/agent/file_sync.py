import logging
from pathlib import Path
from typing import Any

from openai import NotFoundError

logger = logging.getLogger(__name__)


class FileSync:
    """Encapsulates vector store synchronization and file removal helpers."""

    def __init__(self, agent):
        self.agent = agent

    def collect_local_file_ids(self) -> set[str]:
        local_ids: set[str] = set()
        folder = self.agent.files_folder_path
        if not folder or not Path(folder).exists():
            return local_ids
        for entry in Path(folder).iterdir():
            if entry.is_file() and not self._should_skip_file(entry.name):
                try:
                    file_id = self.agent.file_manager.get_id_from_file(entry)
                    if file_id:
                        local_ids.add(file_id)
                except FileNotFoundError:
                    continue
                except Exception as e:
                    logger.debug(f"Agent {self.agent.name}: Skipping file id parse for {entry.name}: {e}")
        return local_ids

    def list_all_vector_store_files(self, vector_store_id: str) -> list[Any]:
        client = self.agent.client_sync
        all_files: list[Any] = []
        after: str | None = None
        while True:
            resp = client.vector_stores.files.list(vector_store_id=vector_store_id, limit=100, after=after)
            data = getattr(resp, "data", [])
            all_files.extend(data)
            has_more = bool(getattr(resp, "has_more", False))
            if not has_more:
                break
            after = getattr(resp, "last_id", None)
            if not isinstance(after, str):
                if data:
                    last = data[-1]
                    after = getattr(last, "id", None)
                else:
                    break
        return all_files

    def sync_with_folder(self) -> None:
        vs_id = self.agent._associated_vector_store_id
        if not vs_id:
            return

        local_file_ids = self.collect_local_file_ids()
        try:
            vs_files = self.list_all_vector_store_files(vs_id)
        except NotFoundError:
            logger.warning(f"Agent {self.agent.name}: Vector Store {vs_id} not found during sync. Skipping cleanup.")
            return

        for vs_file in vs_files:
            file_id = getattr(vs_file, "file_id", None) or getattr(vs_file, "id", None)
            if not isinstance(file_id, str) or file_id in local_file_ids:
                continue

            try:
                self.agent.client_sync.vector_stores.files.delete(vector_store_id=vs_id, file_id=file_id)
                logger.info(
                    f"Agent {self.agent.name}: Removed file {file_id} from Vector Store {vs_id} (not present locally)."
                )
            except NotFoundError:
                pass
            except Exception as e:
                logger.warning(
                    f"Agent {self.agent.name}: Failed to remove file {file_id} from Vector Store {vs_id}: {e}"
                )

            try:
                self.agent.client_sync.files.delete(file_id=file_id)
                logger.info(f"Agent {self.agent.name}: Deleted OpenAI file {file_id} as part of sync.")
            except NotFoundError:
                pass
            except Exception as e:
                logger.warning(f"Agent {self.agent.name}: Failed to delete OpenAI file {file_id}: {e}")

    def remove_file_from_vs_and_oai(self, file_id: str) -> None:
        vs_id = self.agent._associated_vector_store_id
        if vs_id:
            try:
                self.agent.client_sync.vector_stores.files.delete(vector_store_id=vs_id, file_id=file_id)
            except NotFoundError:
                pass
            except Exception as e:
                logger.debug(f"Agent {self.agent.name}: Could not detach file {file_id} from Vector Store {vs_id}: {e}")
        try:
            self.agent.client_sync.files.delete(file_id=file_id)
        except NotFoundError:
            pass
        except Exception as e:
            logger.debug(f"Agent {self.agent.name}: Could not delete OpenAI file {file_id}: {e}")

    def _should_skip_file(self, filename: str) -> bool:
        return filename.startswith(".") or filename.startswith("__")
