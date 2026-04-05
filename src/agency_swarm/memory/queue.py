from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from .types import MemoryWriteJob

if TYPE_CHECKING:
    from .manager import MemoryManager


_JOURNAL_LOCKS: dict[Path, threading.Lock] = {}
_JOURNAL_LOCKS_GUARD = threading.Lock()
_MAX_JOB_ATTEMPTS = 5


class DurableMemoryQueue:
    def __init__(self, *, journal_path: Path, manager: MemoryManager):
        self._journal_path = journal_path
        self._journal_path.parent.mkdir(parents=True, exist_ok=True)
        self._manager = manager
        self._lock = _get_journal_lock(self._journal_path)
        self._start_lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[MemoryWriteJob | None] | None = None
        self._thread: threading.Thread | None = None
        self._closed = False
        if self._has_pending_jobs():
            self._ensure_started()
            self._replay_pending_jobs()

    def enqueue(self, job: MemoryWriteJob) -> None:
        self._ensure_started()
        self._upsert_job(job)
        if self._loop is None or self._queue is None:
            raise RuntimeError("memory queue failed to start")
        self._loop.call_soon_threadsafe(self._queue.put_nowait, job)

    def close(self) -> None:
        self._closed = True
        if self._loop is None or self._thread is None or self._queue is None:
            return
        try:
            future = asyncio.run_coroutine_threadsafe(self._drain_and_stop(), self._loop)
            future.result(timeout=5)
        except Exception:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)  # type: ignore[arg-type]
        self._thread.join(timeout=5)

    def new_job_id(self) -> str:
        return f"memjob_{uuid.uuid4().hex}"

    def _ensure_started(self) -> None:
        if self._closed:
            raise RuntimeError("memory queue is closed")
        with self._start_lock:
            if self._thread is not None:
                return
            self._loop = asyncio.new_event_loop()
            self._queue = asyncio.Queue()
            self._thread = threading.Thread(target=self._run_loop, name="memory-writer", daemon=True)
            self._thread.start()

    def _run_loop(self) -> None:
        if self._loop is None:
            raise RuntimeError("memory queue loop is not initialized")
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._worker())

    async def _worker(self) -> None:
        if self._queue is None:
            raise RuntimeError("memory queue is not initialized")
        while True:
            job = await self._queue.get()
            if job is None:
                self._queue.task_done()
                return
            try:
                job.status = "running"
                job.attempts += 1
                self._upsert_job(job)
                await self._manager.process_job(job)
                job.status = "done"
                job.error = None
                self._upsert_job(job)
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
                self._upsert_job(job)
                if job.attempts >= _MAX_JOB_ATTEMPTS:
                    job.status = "dead_letter"
                    self._upsert_job(job)
                    continue
                await asyncio.sleep(min(2**job.attempts, 30))
                job.status = "queued"
                self._upsert_job(job)
                if self._loop is None or self._queue is None:
                    raise RuntimeError("memory queue is not initialized") from exc
                self._loop.call_soon(self._queue.put_nowait, job)
            finally:
                self._queue.task_done()

    def _replay_pending_jobs(self) -> None:
        if self._loop is None or self._queue is None:
            return
        for payload in self._load_jobs():
            if payload.get("status") in {"queued", "running", "failed"}:
                job = _deserialize_job(payload)
                job.status = "queued"
                self._loop.call_soon_threadsafe(self._queue.put_nowait, job)

    def _has_pending_jobs(self) -> bool:
        return any(payload.get("status") in {"queued", "running", "failed"} for payload in self._load_jobs())

    def _load_jobs(self) -> list[dict]:
        if not self._journal_path.exists():
            return []
        data = self._journal_path.read_text(encoding="utf-8").strip()
        if not data:
            return []
        return json.loads(data)

    def _upsert_job(self, job: MemoryWriteJob) -> None:
        with self._lock:
            jobs = self._load_jobs()
            serialized = _serialize_job(job)
            jobs = [payload for payload in jobs if payload.get("status") not in {"done"}]
            for index, payload in enumerate(jobs):
                if payload["job_id"] == job.job_id:
                    jobs[index] = serialized
                    break
            else:
                jobs.append(serialized)
            jobs = [payload for payload in jobs if payload.get("status") not in {"done"}]
            temp_path = self._journal_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(jobs, indent=2), encoding="utf-8")
            temp_path.replace(self._journal_path)

    async def _drain_and_stop(self) -> None:
        if self._queue is None:
            return
        await self._queue.join()
        await self._queue.put(None)  # type: ignore[arg-type]


def _get_journal_lock(path: Path) -> threading.Lock:
    resolved = path.resolve()
    with _JOURNAL_LOCKS_GUARD:
        lock = _JOURNAL_LOCKS.get(resolved)
        if lock is None:
            lock = threading.Lock()
            _JOURNAL_LOCKS[resolved] = lock
        return lock


def _serialize_job(job: MemoryWriteJob) -> dict:
    payload = asdict(job)
    payload["enqueued_at"] = int(time.time())
    return payload


def _deserialize_job(payload: dict) -> MemoryWriteJob:
    from .types import MemoryIdentity, MemoryOperation, MemoryScope, MemoryType, MemoryWriteRequest

    request_payload = payload["request"]
    request = MemoryWriteRequest(
        operation=MemoryOperation(request_payload["operation"]),
        content=request_payload["content"],
        rationale=request_payload["rationale"],
        scope=MemoryScope(request_payload["scope"]),
        memory_type=MemoryType(request_payload["memory_type"]),
        source_agent=request_payload["source_agent"],
        memory_identity=MemoryIdentity(**request_payload["memory_identity"]),
        context_snapshot=request_payload["context_snapshot"],
        requested_providers=request_payload.get("requested_providers"),
        record_id=request_payload.get("record_id"),
        title=request_payload.get("title"),
    )
    return MemoryWriteJob(
        job_id=payload["job_id"],
        request=request,
        provider_names=payload["provider_names"],
        status=payload.get("status", "queued"),
        attempts=int(payload.get("attempts", 0)),
        error=payload.get("error"),
    )
