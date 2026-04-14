from __future__ import annotations

import json
import logging
import re
import threading
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from agency_swarm.memory.provider import MemoryProvider
from agency_swarm.memory.types import (
    CanonicalMemoryWrite,
    MemoryIdentity,
    MemoryProviderCapabilities,
    MemoryRecord,
    MemoryScope,
    MemoryType,
)

logger = logging.getLogger(__name__)

fcntl_module: Any | None
try:
    import fcntl as fcntl_module
except ImportError:  # pragma: no cover - Windows fallback
    fcntl_module = None

_DOCUMENT_HEADER = "# Durable Memory\n\n<!-- agency-swarm-memory-v1 -->\n"
_RECORD_START_MARKER = "<!-- memory-record-start -->"
_RECORD_END_MARKER = "<!-- memory-record-end -->"
_ESCAPED_RECORD_START_MARKER = "&lt;!-- memory-record-start --&gt;"
_ESCAPED_RECORD_END_MARKER = "&lt;!-- memory-record-end --&gt;"
_RECORD_PATTERN = re.compile(
    rf"{re.escape(_RECORD_START_MARKER)}\n(?P<body>.*?)\n{re.escape(_RECORD_END_MARKER)}",
    re.DOTALL,
)
_MAX_FILE_LOCKS = 1024


@dataclass
class _TrackedFileLock:
    lock: threading.Lock
    borrowers: int = 0


_FILE_LOCKS: OrderedDict[Path, _TrackedFileLock] = OrderedDict()
_FILE_LOCKS_GUARD = threading.Lock()


class MarkdownMemoryProvider(MemoryProvider):
    def __init__(self, *, name: str, path_template: str):
        self.name = name
        self.path_template = path_template
        self.capabilities = MemoryProviderCapabilities(
            system_recall=True,
            agentic_search=True,
            write=True,
            delete=True,
        )

    async def recall_system(
        self,
        *,
        memory_identity: MemoryIdentity,
        agent_name: str,
        scopes: tuple[MemoryScope, ...],
        limit: int,
    ) -> list[MemoryRecord]:
        records = await self._load_records(
            memory_identity=memory_identity,
            agent_name=agent_name,
            scopes=scopes,
            memory_type=MemoryType.SYSTEM,
        )
        return records[:limit]

    async def search_agentic(
        self,
        *,
        query: str,
        memory_identity: MemoryIdentity,
        agent_name: str,
        scopes: tuple[MemoryScope, ...],
        limit: int,
    ) -> list[MemoryRecord]:
        records = await self._load_records(
            memory_identity=memory_identity,
            agent_name=agent_name,
            scopes=scopes,
            memory_type=MemoryType.AGENTIC,
        )
        if not query.strip():
            return records[:limit]
        lowered = query.lower()
        matches = [
            record for record in records if lowered in record.content.lower() or lowered in (record.title or "").lower()
        ]
        return matches[:limit]

    async def apply_write(
        self,
        *,
        write: CanonicalMemoryWrite,
        memory_identity: MemoryIdentity,
        agent_name: str,
    ) -> MemoryRecord:
        owner_id = memory_identity.resolve_scope_owner(write.scope, agent_name=agent_name)
        file_path = self._resolve_path(write.scope.value, write.memory_type.value, owner_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with _acquire_file_lock(file_path), _acquire_process_lock(_lock_path_for(file_path)):
            records = self._read_records(file_path)

            new_record = MemoryRecord(
                record_id=write.record_id,
                provider_name=self.name,
                scope=write.scope,
                memory_type=write.memory_type,
                owner_id=owner_id,
                title=write.title,
                content=write.content,
                metadata=dict(write.metadata),
            )

            updated = False
            for index, record in enumerate(records):
                if record.record_id == write.record_id:
                    records[index] = new_record
                    updated = True
                    break
            if not updated:
                records.append(new_record)

            self._write_records(file_path, records)
            return new_record

    async def delete_record(self, *, record_id: str, memory_identity: MemoryIdentity, agent_name: str) -> None:
        for scope in MemoryScope:
            for memory_type in MemoryType:
                try:
                    owner_id = memory_identity.resolve_scope_owner(scope, agent_name=agent_name)
                except ValueError:
                    continue
                file_path = self._resolve_path(scope.value, memory_type.value, owner_id)
                with _acquire_file_lock(file_path), _acquire_process_lock(_lock_path_for(file_path)):
                    records = self._read_records(file_path)
                    filtered = [record for record in records if record.record_id != record_id]
                    if len(filtered) == len(records):
                        continue
                    self._write_records(file_path, filtered)
                    return

    async def _load_records(
        self,
        *,
        memory_identity: MemoryIdentity,
        agent_name: str,
        scopes: tuple[MemoryScope, ...],
        memory_type: MemoryType,
    ) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        for scope in scopes:
            try:
                owner_id = memory_identity.resolve_scope_owner(scope, agent_name=agent_name)
            except ValueError:
                continue
            file_path = self._resolve_path(scope.value, memory_type.value, owner_id)
            with _acquire_file_lock(file_path):
                records.extend(self._read_records(file_path))
        return records

    def _resolve_path(self, scope: str, memory_type: str, owner_id: str) -> Path:
        return Path(
            self.path_template.format(
                scope=_sanitize_path_component(scope),
                memory_type=_sanitize_path_component(memory_type),
                owner_id=_sanitize_path_component(owner_id),
            )
        )

    def _read_records(self, file_path: Path) -> list[MemoryRecord]:
        if not file_path.exists():
            return []
        text = file_path.read_text(encoding="utf-8").strip()
        if not text:
            return []

        records: list[MemoryRecord] = []
        for match in _RECORD_PATTERN.finditer(text):
            try:
                records.append(self._parse_record(match.group("body")))
            except ValueError as exc:
                logger.warning("Skipping malformed markdown memory record in %s: %s", file_path, exc)
        return records

    def _write_records(self, file_path: Path, records: list[MemoryRecord]) -> None:
        body = _DOCUMENT_HEADER
        if records:
            body += "\n\n".join(self._render_record(record) for record in records) + "\n"
        temp_path = file_path.with_suffix(f"{file_path.suffix}.tmp")
        temp_path.write_text(body, encoding="utf-8")
        temp_path.replace(file_path)

    def _render_record(self, record: MemoryRecord) -> str:
        title = record.title or "Untitled memory"
        metadata_text = json.dumps(record.metadata, sort_keys=True, ensure_ascii=True)
        return "\n".join(
            [
                _RECORD_START_MARKER,
                f"## {record.record_id}",
                f"title: {title}",
                f"provider: {record.provider_name}",
                f"scope: {record.scope.value}",
                f"memory_type: {record.memory_type.value}",
                f"owner_id: {record.owner_id}",
                f"metadata: {metadata_text}",
                "",
                _escape_record_content(record.content.strip()),
                _RECORD_END_MARKER,
            ]
        )

    def _parse_record(self, body: str) -> MemoryRecord:
        metadata_block, separator, content = body.partition("\n\n")
        if not separator:
            raise ValueError("record body is missing content separator")

        lines = metadata_block.splitlines()
        if not lines or not lines[0].startswith("## "):
            raise ValueError("record body is missing record heading")

        record_id = lines[0][3:].strip()
        values: dict[str, str] = {}
        for line in lines[1:]:
            key, sep, value = line.partition(": ")
            if not sep:
                raise ValueError(f"malformed metadata line: {line}")
            values[key] = value

        metadata = json.loads(values.get("metadata", "{}"))
        if not isinstance(metadata, dict):
            raise ValueError("record metadata must be a JSON object")

        return MemoryRecord(
            record_id=record_id,
            provider_name=values["provider"],
            scope=MemoryScope(values["scope"]),
            memory_type=MemoryType(values["memory_type"]),
            owner_id=values["owner_id"],
            title=values.get("title"),
            content=_unescape_record_content(content.strip()),
            metadata=metadata,
        )


@contextmanager
def _borrow_file_lock(path: Path) -> Iterator[threading.Lock]:
    resolved = path.resolve()
    with _FILE_LOCKS_GUARD:
        tracked_lock = _FILE_LOCKS.get(resolved)
        if tracked_lock is None:
            tracked_lock = _TrackedFileLock(lock=threading.Lock())
            _FILE_LOCKS[resolved] = tracked_lock
        else:
            _FILE_LOCKS.move_to_end(resolved)
        tracked_lock.borrowers += 1
        _trim_file_locks()
        lock = tracked_lock.lock
    try:
        yield lock
    finally:
        with _FILE_LOCKS_GUARD:
            current = _FILE_LOCKS.get(resolved)
            if current is tracked_lock:
                current.borrowers -= 1
                _trim_file_locks()


@contextmanager
def _acquire_file_lock(path: Path) -> Iterator[None]:
    with _borrow_file_lock(path) as lock:
        with lock:
            yield


def _sanitize_path_component(value: str) -> str:
    return quote(value, safe="")


@contextmanager
def _acquire_process_lock(lock_path: Path) -> Iterator[None]:
    if fcntl_module is None:
        yield
        return

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_EX)
        try:
            yield
        finally:
            fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_UN)


def _escape_record_content(content: str) -> str:
    return content.replace(_RECORD_START_MARKER, _ESCAPED_RECORD_START_MARKER).replace(
        _RECORD_END_MARKER, _ESCAPED_RECORD_END_MARKER
    )


def _unescape_record_content(content: str) -> str:
    return content.replace(_ESCAPED_RECORD_START_MARKER, _RECORD_START_MARKER).replace(
        _ESCAPED_RECORD_END_MARKER, _RECORD_END_MARKER
    )


def _trim_file_locks() -> None:
    while len(_FILE_LOCKS) > _MAX_FILE_LOCKS:
        oldest_path, tracked_lock = next(iter(_FILE_LOCKS.items()))
        if tracked_lock.borrowers > 0 or tracked_lock.lock.locked():
            _FILE_LOCKS.move_to_end(oldest_path)
            break
        _FILE_LOCKS.popitem(last=False)


def _lock_path_for(file_path: Path) -> Path:
    return file_path.with_suffix(f"{file_path.suffix}.lock")
