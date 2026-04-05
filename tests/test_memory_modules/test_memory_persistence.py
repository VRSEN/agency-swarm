from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest

from agency_swarm.memory import (
    AgentMemoryConfig,
    CanonicalMemoryWrite,
    MarkdownMemoryProviderConfig,
    MemoryConfig,
    MemoryIdentity,
    MemoryManager,
    MemoryOperation,
    MemoryPermissionDecision,
    MemoryScope,
    MemoryType,
    MemoryWriteRequest,
)
from agency_swarm.memory.normalizer import MemoryNormalizer


class StaticMemoryNormalizer(MemoryNormalizer):
    async def normalize(
        self,
        *,
        request: MemoryWriteRequest,
        existing_records,
        model=None,
    ) -> CanonicalMemoryWrite:
        return CanonicalMemoryWrite(
            record_id=request.record_id or "mem_persisted",
            scope=request.scope,
            memory_type=request.memory_type,
            title=request.title or "Persisted memory",
            content=request.content,
            metadata={"existing_count": len(existing_records)},
        )


async def _allow_all(*_args, **_kwargs):
    return MemoryPermissionDecision.allow()


async def _wait_for_file(path: Path, expected_text: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if path.exists() and expected_text in path.read_text(encoding="utf-8"):
            return
        await asyncio.sleep(0.05)
    pytest.fail(f"timed out waiting for memory file {path}")


@pytest.mark.asyncio
async def test_markdown_memory_persists_across_manager_restart(tmp_path: Path) -> None:
    path_template = str(tmp_path / "{scope}" / "{memory_type}" / "{owner_id}.md")
    config = MemoryConfig(
        providers=[MarkdownMemoryProviderConfig(path_template=path_template)],
        journal_path=tmp_path / "jobs.json",
        normalizer=StaticMemoryNormalizer(),
        permission_resolver=_allow_all,
    )
    identity = MemoryIdentity(user_id="user-1", agency_id="agency-1")
    record_path = Path(path_template.format(scope="user", memory_type="system", owner_id="user-1"))

    manager = MemoryManager(config)
    try:
        decision = await manager.request_write(
            request=MemoryWriteRequest(
                operation=MemoryOperation.SAVE,
                content="User prefers weekly summaries",
                rationale="Stable reporting preference",
                scope=MemoryScope.USER,
                memory_type=MemoryType.SYSTEM,
                source_agent="Support",
                memory_identity=identity,
                context_snapshot=[{"role": "user", "content": "Please send weekly summaries."}],
            ),
            runtime_context=None,
            agent_config=AgentMemoryConfig(),
        )
        assert decision.mode.value == "allow"
        await _wait_for_file(record_path, "User prefers weekly summaries")
    finally:
        manager.close()

    manager_after_restart = MemoryManager(config)
    try:
        recalled = await manager_after_restart.build_system_memory(
            memory_identity=identity,
            agent_name="Support",
            agent_config=AgentMemoryConfig(),
        )
        assert recalled is not None
        assert "User prefers weekly summaries" in recalled
        assert "Durable memory" in recalled
    finally:
        manager_after_restart.close()


def test_memory_manager_does_not_spawn_writer_thread_until_enqueue(tmp_path: Path) -> None:
    config = MemoryConfig.markdown(
        folder=tmp_path,
        journal_path=tmp_path / "jobs.json",
        normalizer=StaticMemoryNormalizer(),
    )

    before = [thread.name for thread in threading.enumerate() if thread.name == "memory-writer"]
    manager = MemoryManager(config)
    try:
        after_init = [thread.name for thread in threading.enumerate() if thread.name == "memory-writer"]
        assert after_init == before
    finally:
        manager.close()


@pytest.mark.asyncio
async def test_markdown_memory_handles_parallel_managers_sharing_a_journal(tmp_path: Path) -> None:
    config = MemoryConfig.markdown(
        folder=tmp_path / "memory",
        journal_path=tmp_path / "jobs.json",
        normalizer=StaticMemoryNormalizer(),
        permission_resolver=_allow_all,
    )
    identity = MemoryIdentity(user_id="user-1", agency_id="agency-1")
    record_path = tmp_path / "memory" / "user" / "system" / "user-1.md"

    manager_one = MemoryManager(config)
    manager_two = MemoryManager(config)
    try:
        await asyncio.gather(
            manager_one.request_write(
                request=MemoryWriteRequest(
                    operation=MemoryOperation.SAVE,
                    content="User prefers weekly summaries",
                    rationale="Stable reporting preference",
                    scope=MemoryScope.USER,
                    memory_type=MemoryType.SYSTEM,
                    source_agent="Support",
                    memory_identity=identity,
                    context_snapshot=[],
                    record_id="mem_one",
                ),
                runtime_context=None,
                agent_config=AgentMemoryConfig(),
            ),
            manager_two.request_write(
                request=MemoryWriteRequest(
                    operation=MemoryOperation.SAVE,
                    content="User prefers concise replies",
                    rationale="Stable style preference",
                    scope=MemoryScope.USER,
                    memory_type=MemoryType.SYSTEM,
                    source_agent="Support",
                    memory_identity=identity,
                    context_snapshot=[],
                    record_id="mem_two",
                ),
                runtime_context=None,
                agent_config=AgentMemoryConfig(),
            ),
        )
        await _wait_for_file(record_path, "User prefers weekly summaries")
        await _wait_for_file(record_path, "User prefers concise replies")
    finally:
        manager_one.close()
        manager_two.close()


@pytest.mark.asyncio
async def test_markdown_memory_sanitizes_owner_id_before_writing(tmp_path: Path) -> None:
    sandbox = tmp_path / "sandbox"
    config = MemoryConfig.markdown(
        folder=sandbox / "memory",
        journal_path=sandbox / "jobs.json",
        normalizer=StaticMemoryNormalizer(),
        permission_resolver=_allow_all,
    )
    identity = MemoryIdentity(user_id="../../../../escaped", agency_id="agency-1")

    manager = MemoryManager(config)
    try:
        decision = await manager.request_write(
            request=MemoryWriteRequest(
                operation=MemoryOperation.SAVE,
                content="User prefers weekly summaries",
                rationale="Stable reporting preference",
                scope=MemoryScope.USER,
                memory_type=MemoryType.SYSTEM,
                source_agent="Support",
                memory_identity=identity,
                context_snapshot=[],
                record_id="mem_path_safe",
            ),
            runtime_context=None,
            agent_config=AgentMemoryConfig(),
        )
        assert decision.mode.value == "allow"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            files = list((sandbox / "memory").rglob("*.md"))
            if files:
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("timed out waiting for sanitized markdown memory file")

        assert len(files) == 1
        assert files[0].is_relative_to(sandbox / "memory")
        assert not (tmp_path / "escaped.md").exists()
        assert "escaped" in files[0].name
    finally:
        manager.close()
