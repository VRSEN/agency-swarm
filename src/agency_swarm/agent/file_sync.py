import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openai import NotFoundError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent


class FileSync:
    """Encapsulates vector store synchronization and file removal helpers."""

    def __init__(self, agent: "Agent") -> None:  # noqa: UP037
        self.agent: "Agent" = agent  # noqa: UP037

    def collect_local_file_ids(self) -> set[str]:
        local_ids: set[str] = set()
        folder = self.agent.files_folder_path
        if not folder or not Path(folder).exists():
            return local_ids
        file_manager = self.agent.file_manager
        if file_manager is None:
            raise RuntimeError(f"Agent {self.agent.name}: File manager is not initialized")
        for entry in Path(folder).iterdir():
            if entry.is_file() and not self._should_skip_file(entry.name):
                try:
                    file_id = file_manager.get_id_from_file(entry)
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
            list_kwargs: dict[str, Any] = {"vector_store_id": vector_store_id, "limit": 100}
            if after is not None:
                list_kwargs["after"] = after
            resp = client.vector_stores.files.list(**list_kwargs)
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

        orphan_file_ids: list[str] = []
        for vs_file in vs_files:
            file_id = getattr(vs_file, "file_id", None) or getattr(vs_file, "id", None)
            if not isinstance(file_id, str) or file_id in local_file_ids:
                continue

            orphan_file_ids.append(file_id)

        if not orphan_file_ids:
            return

        logger.info(
            "Agent %s: Rebuilding vector store %s to remove orphaned files %s.",
            self.agent.name,
            vs_id,
            orphan_file_ids,
        )
        self._rebuild_vector_store()

        for file_id in orphan_file_ids:
            try:
                self.agent.client_sync.files.delete(file_id=file_id)
                logger.info("Agent %s: Deleted OpenAI file %s during vector store rebuild.", self.agent.name, file_id)
                self._wait_for_openai_file_absence(file_id)
            except NotFoundError:
                continue
            except Exception as exc:
                logger.warning(
                    "Agent %s: Failed to delete OpenAI file %s during rebuild: %s",
                    self.agent.name,
                    file_id,
                    exc,
                )

    def remove_file_from_vs_and_oai(self, file_id: str) -> None:
        vs_id = self.agent._associated_vector_store_id
        if vs_id:
            try:
                self.agent.client_sync.vector_stores.files.delete(vector_store_id=vs_id, file_id=file_id)
                self._wait_for_vector_store_file_absence(vector_store_id=vs_id, file_id=file_id)
            except NotFoundError:
                pass
            except Exception as e:
                logger.debug(f"Agent {self.agent.name}: Could not detach file {file_id} from Vector Store {vs_id}: {e}")
        try:
            self.agent.client_sync.files.delete(file_id=file_id)
            self._wait_for_openai_file_absence(file_id)
        except NotFoundError:
            pass
        except Exception as e:
            logger.debug(f"Agent {self.agent.name}: Could not delete OpenAI file {file_id}: {e}")

    def _should_skip_file(self, filename: str) -> bool:
        return filename.startswith(".") or filename.startswith("__")

    def wait_for_vector_store_file_ready(
        self, *, vector_store_id: str, file_id: str, timeout_seconds: float = 120.0
    ) -> None:
        """Poll until the file appears in the vector store with status completed or timing out."""
        deadline = time.monotonic() + timeout_seconds
        logged_wait = False
        while time.monotonic() < deadline:
            try:
                vs_file = self.agent.client_sync.vector_stores.files.retrieve(
                    vector_store_id=vector_store_id,
                    file_id=file_id,
                )
            except NotFoundError:
                if not logged_wait:
                    logger.debug(
                        "Agent %s: Waiting for file %s to appear in Vector Store %s.",
                        self.agent.name,
                        file_id,
                        vector_store_id,
                    )
                    logged_wait = True
                time.sleep(1.0)
                continue
            except Exception as exc:
                logger.warning(
                    "Agent %s: Error polling Vector Store %s for file %s: %s",
                    self.agent.name,
                    vector_store_id,
                    file_id,
                    exc,
                )
                return

            status = getattr(vs_file, "status", None)
            if status == "completed":
                logger.info(
                    "Agent %s: File %s is ready in Vector Store %s.",
                    self.agent.name,
                    file_id,
                    vector_store_id,
                )
                return
            if status == "failed":
                logger.error(
                    "Agent %s: Vector Store %s reported failure ingesting file %s.",
                    self.agent.name,
                    vector_store_id,
                    file_id,
                )
                return
            time.sleep(1.0)

        logger.warning(
            "Agent %s: Timed out waiting for file %s to finish processing in Vector Store %s.",
            self.agent.name,
            file_id,
            vector_store_id,
        )

    def _wait_for_vector_store_file_absence(
        self, *, vector_store_id: str, file_id: str, timeout_seconds: float = 60.0
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        warned = False
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self.agent.client_sync.vector_stores.files.retrieve(vector_store_id=vector_store_id, file_id=file_id)
            except NotFoundError:
                return
            except Exception as exc:
                last_error = exc
                if not warned:
                    logger.warning(
                        "Agent %s: Error while polling deletion of %s from Vector Store %s: %s",
                        self.agent.name,
                        file_id,
                        vector_store_id,
                        exc,
                    )
                    warned = True
                time.sleep(1.0)
                continue
            time.sleep(1.0)
        if last_error:
            logger.warning(
                "Agent %s: Timed out waiting for file %s to disappear from Vector Store %s (last error: %s).",
                self.agent.name,
                file_id,
                vector_store_id,
                last_error,
            )

    def _rebuild_vector_store(self) -> None:
        folder_path = getattr(self.agent, "files_folder_path", None)
        if not folder_path or not Path(folder_path).exists():
            logger.warning("Agent %s: Cannot rebuild vector store; folder path is not available.", self.agent.name)
            return

        folder_path = Path(folder_path)
        base_name = folder_path.name
        match = re.match(r"^(.+)_vs_[A-Za-z0-9]{15,}$", base_name)
        base_prefix = match.group(1) if match else base_name

        old_vs_id = getattr(self.agent, "_associated_vector_store_id", None)

        try:
            new_vs = self.agent.client_sync.vector_stores.create(name=base_prefix)
        except Exception as exc:
            logger.error("Agent %s: Failed to create replacement vector store: %s", self.agent.name, exc)
            return

        new_folder_name = f"{base_prefix}_vs_{new_vs.id}"
        new_folder_path = folder_path.parent / new_folder_name

        try:
            folder_path.rename(new_folder_path)
        except Exception as exc:
            logger.error(
                "Agent %s: Failed to rename folder %s to %s during vector store rebuild: %s",
                self.agent.name,
                folder_path,
                new_folder_path,
                exc,
            )
            try:
                self.agent.client_sync.vector_stores.delete(new_vs.id)
            except Exception:
                pass
            return

        self.agent.files_folder_path = new_folder_path.resolve()
        self.agent.files_folder = str(new_folder_path)
        self.agent._associated_vector_store_id = new_vs.id

        file_manager = getattr(self.agent, "file_manager", None)
        if file_manager is None:
            logger.error("Agent %s: File manager is not initialized; cannot rebuild vector store.", self.agent.name)
            return

        try:
            from agents import FileSearchTool  # type: ignore[import]
        except Exception:  # pragma: no cover - defensive
            FileSearchTool = None  # type: ignore

        if FileSearchTool is not None:
            self.agent.tools = [tool for tool in self.agent.tools if not isinstance(tool, FileSearchTool)]

        for entry in new_folder_path.iterdir():
            if not entry.is_file() or self._should_skip_file(entry.name):
                continue
            file_id = file_manager.get_id_from_file(entry)
            if not file_id:
                continue
            stem = entry.stem
            suffix = entry.suffix
            new_name = re.sub(r"_file-[A-Za-z0-9]{15,}$", "", stem) + suffix
            new_path = entry.with_name(new_name)
            if new_path != entry:
                entry.rename(new_path)

        for entry in sorted(new_folder_path.iterdir()):
            if entry.is_file() and not self._should_skip_file(entry.name):
                file_manager.upload_file(str(entry), include_in_vector_store=True)

        file_manager.add_file_search_tool(vector_store_id=new_vs.id)

        if old_vs_id and old_vs_id != new_vs.id:
            try:
                self.agent.client_sync.vector_stores.delete(old_vs_id)
            except Exception as exc:
                logger.warning(
                    "Agent %s: Failed to delete old vector store %s during rebuild: %s",
                    self.agent.name,
                    old_vs_id,
                    exc,
                )

    def _wait_for_openai_file_absence(self, file_id: str, timeout_seconds: float = 60.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        warned = False
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self.agent.client_sync.files.retrieve(file_id)
            except NotFoundError:
                return
            except Exception as exc:
                last_error = exc
                if not warned:
                    logger.warning(
                        "Agent %s: Error while polling deletion of OpenAI file %s: %s",
                        self.agent.name,
                        file_id,
                        exc,
                    )
                    warned = True
                time.sleep(1.0)
                continue
            time.sleep(1.0)
        if last_error:
            logger.warning(
                "Agent %s: Timed out waiting for OpenAI file %s to be fully deleted (last error: %s).",
                self.agent.name,
                file_id,
                last_error,
            )
        else:
            logger.warning(
                "Agent %s: Timed out waiting for OpenAI file %s to be fully deleted.",
                self.agent.name,
                file_id,
            )
