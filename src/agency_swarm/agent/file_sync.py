from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from agents.exceptions import AgentsException
from openai import NotFoundError, OpenAI
from openai._types import NOT_GIVEN, omit
from openai.types.vector_stores import VectorStoreFile

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from agency_swarm.agent.core import Agent


class FileSync:
    """Encapsulates vector store synchronization and file removal helpers."""

    def __init__(self, agent: Agent) -> None:
        self.agent: Agent = agent

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

    def list_all_vector_store_files(self, vector_store_id: str) -> list[VectorStoreFile]:
        client: OpenAI = self.agent.client_sync
        all_files: list[VectorStoreFile] = []
        after_cursor: str | None = None
        while True:
            resp = client.vector_stores.files.list(
                vector_store_id=vector_store_id,
                limit=100,
                after=after_cursor if after_cursor is not None else omit,
            )

            data = resp.data
            all_files.extend(data)

            next_cursor: str | None = None
            has_more = bool(resp.has_more)

            if has_more:
                page_info = resp.next_page_info()
                if page_info is not None:
                    params = page_info.params
                    if params is not NOT_GIVEN and isinstance(params, Mapping):
                        after_candidate = params.get("after")
                        if isinstance(after_candidate, str):
                            next_cursor = after_candidate

            if next_cursor is None and has_more and data:
                candidate = data[-1].id
                if isinstance(candidate, str):
                    next_cursor = candidate

            if next_cursor is None:
                break

            after_cursor = next_cursor
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
            file_id = vs_file.id
            if file_id in local_file_ids:
                continue

            orphan_file_ids.append(file_id)

        for file_id in orphan_file_ids:
            try:
                # OpenAI file deletion removes the file from all vector stores.
                self.agent.client_sync.files.delete(file_id=file_id)
                logger.info("Agent %s: Deleted OpenAI file %s as part of sync.", self.agent.name, file_id)
            except NotFoundError:
                logger.debug("Agent %s: OpenAI file %s already absent during sync.", self.agent.name, file_id)
            except Exception as exc:
                logger.warning(
                    "Agent %s: Failed to delete OpenAI file %s during sync: %s",
                    self.agent.name,
                    file_id,
                    exc,
                )
            finally:
                self._wait_for_vector_store_file_absence(vector_store_id=vs_id, file_id=file_id)
                self._wait_for_openai_file_absence(file_id)

    def remove_file_from_vs_and_oai(self, file_id: str) -> None:
        vs_id = self.agent._associated_vector_store_id

        try:
            # OpenAI file deletion removes the file from all vector stores.
            self.agent.client_sync.files.delete(file_id=file_id)
        except NotFoundError:
            pass
        except Exception as exc:
            logger.debug(f"Agent {self.agent.name}: Could not delete OpenAI file {file_id}: {exc}")
        finally:
            if vs_id:
                self._wait_for_vector_store_file_absence(vector_store_id=vs_id, file_id=file_id)
            self._wait_for_openai_file_absence(file_id)

    def _should_skip_file(self, filename: str) -> bool:
        return filename.startswith(".") or filename.startswith("__")

    def wait_for_vector_store_files_ready(
        self,
        entries: list[tuple[str, str]],
        timeout_seconds: float = 120.0,
    ) -> None:
        """Poll until all provided files reach ``completed`` status or raise/timeout."""
        if not entries:
            return

        deadline = time.monotonic() + timeout_seconds
        backoff = 0.5
        max_backoff = 5.0

        pending: dict[str, set[str]] = {}
        warned_wait: set[tuple[str, str]] = set()
        for vector_store_id, file_id in entries:
            pending.setdefault(vector_store_id, set()).add(file_id)

        while pending:
            now = time.monotonic()
            if now >= deadline:
                for vector_store_id, file_ids in pending.items():
                    logger.warning(
                        "Agent %s: Timed out waiting for files %s to finish processing in Vector Store %s.",
                        self.agent.name,
                        sorted(file_ids),
                        vector_store_id,
                    )
                return

            completed: list[tuple[str, str]] = []
            for vector_store_id, file_ids in pending.items():
                for file_id in list(file_ids):
                    try:
                        vs_file = self.agent.client_sync.vector_stores.files.retrieve(
                            vector_store_id=vector_store_id,
                            file_id=file_id,
                        )
                    except NotFoundError:
                        if (vector_store_id, file_id) not in warned_wait:
                            logger.debug(
                                "Agent %s: Waiting for file %s to appear in Vector Store %s.",
                                self.agent.name,
                                file_id,
                                vector_store_id,
                            )
                            warned_wait.add((vector_store_id, file_id))
                        continue
                    except Exception as exc:
                        if (vector_store_id, file_id) not in warned_wait:
                            logger.warning(
                                "Agent %s: Error polling Vector Store %s for file %s: %s",
                                self.agent.name,
                                vector_store_id,
                                file_id,
                                exc,
                            )
                            warned_wait.add((vector_store_id, file_id))
                        continue

                    status = vs_file.status
                    if status == "completed":
                        logger.info(
                            "Agent %s: File %s is ready in Vector Store %s.",
                            self.agent.name,
                            file_id,
                            vector_store_id,
                        )
                        completed.append((vector_store_id, file_id))
                        continue

                    if status in {"failed", "cancelled"}:
                        last_error = getattr(vs_file, "last_error", None)
                        if last_error and getattr(last_error, "message", None):
                            error_detail = (
                                f" Details: code={getattr(last_error, 'code', 'unknown')}, message={last_error.message}"
                            )
                        else:
                            error_detail = ""
                        logger.error(
                            "Agent %s: Vector Store %s returned status %s for file %s.%s",
                            self.agent.name,
                            vector_store_id,
                            status,
                            file_id,
                            error_detail,
                        )
                        raise AgentsException(
                            f"Vector Store {vector_store_id} reported status {status} "
                            f"while processing file {file_id}{error_detail}"
                        )

            for vector_store_id, file_id in completed:
                pending[vector_store_id].discard(file_id)
                warned_wait.discard((vector_store_id, file_id))
                if not pending[vector_store_id]:
                    pending.pop(vector_store_id, None)

            if pending:
                progress_made = bool(completed)
                sleep_interval = 0.5 if progress_made else backoff
                time.sleep(sleep_interval)
                if progress_made:
                    backoff = min(0.5 * 1.7, max_backoff)
                else:
                    backoff = min(backoff * 1.7, max_backoff)
            else:
                backoff = 0.5

    def wait_for_vector_store_file_ready(
        self, *, vector_store_id: str, file_id: str, timeout_seconds: float = 120.0
    ) -> None:
        """Backward-compatible wrapper for single file readiness polling."""
        self.wait_for_vector_store_files_ready(
            [(vector_store_id, file_id)],
            timeout_seconds=timeout_seconds,
        )

    def _wait_for_vector_store_file_absence(
        self, *, vector_store_id: str, file_id: str, timeout_seconds: float = 120.0
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        warned = False
        last_error: Exception | None = None
        backoff = 0.5
        max_backoff = 5.0
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
                time.sleep(backoff)
                backoff = min(backoff * 1.7, max_backoff)
                continue
            time.sleep(backoff)
            backoff = min(backoff * 1.7, max_backoff)
        if last_error:
            logger.warning(
                "Agent %s: Timed out after %.0fs waiting for file %s to disappear from Vector Store %s "
                "(last error: %s). "
                "OpenAI list endpoint still reports the id despite deletion.",
                self.agent.name,
                timeout_seconds,
                file_id,
                vector_store_id,
                last_error,
            )
        else:
            logger.warning(
                "Agent %s: Timed out after %.0fs waiting for file %s to disappear from Vector Store %s. "
                "OpenAI list endpoint still reports the id despite deletion.",
                self.agent.name,
                timeout_seconds,
                file_id,
                vector_store_id,
            )

    def _wait_for_openai_file_absence(self, file_id: str, timeout_seconds: float = 120.0) -> None:
        deadline = time.monotonic() + timeout_seconds
        warned = False
        last_error: Exception | None = None
        backoff = 0.5
        max_backoff = 5.0
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
                time.sleep(backoff)
                backoff = min(backoff * 1.7, max_backoff)
                continue
            time.sleep(backoff)
            backoff = min(backoff * 1.7, max_backoff)
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
