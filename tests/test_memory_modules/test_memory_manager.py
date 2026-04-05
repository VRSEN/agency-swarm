from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from agency_swarm.memory import (
    AgentMemoryConfig,
    CanonicalMemoryWrite,
    MarkdownMemoryProviderConfig,
    Mem0MemoryProviderConfig,
    Memory,
    MemoryConfig,
    MemoryIdentity,
    MemoryManager,
    MemoryOperation,
    MemoryPermissionDecision,
    MemoryScope,
    MemoryType,
    MemoryWriteRequest,
    OpenAIFileSearchMemoryProviderConfig,
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
            record_id=request.record_id or "mem_static",
            scope=request.scope,
            memory_type=request.memory_type,
            title=request.title or "Normalized memory",
            content=request.content,
            metadata={"existing_count": len(existing_records)},
        )


class _VectorStoreSearchClient:
    def __init__(self) -> None:
        self.vector_stores = self
        self.calls: list[dict[str, object | None]] = []

    async def search(
        self,
        *,
        vector_store_id: str,
        query: str,
        filters=None,
        max_num_results: int,
    ):
        self.calls.append(
            {
                "vector_store_id": vector_store_id,
                "query": query,
                "filters": filters,
                "max_num_results": max_num_results,
            }
        )

        class _Result:
            def __init__(self) -> None:
                self.file_id = f"{vector_store_id}-file"
                self.filename = "memory.md"
                self.content = [type("_Chunk", (), {"text": f"match for {query}"})()]

        return type("_Page", (), {"data": [_Result()]})()


@pytest.fixture
def markdown_config(tmp_path: Path) -> MemoryConfig:
    return MemoryConfig.markdown(
        folder=tmp_path,
        journal_path=tmp_path / "jobs.json",
        normalizer=StaticMemoryNormalizer(),
    )


def test_markdown_memory_config_shortcut_builds_default_provider(tmp_path: Path) -> None:
    config = Memory.markdown(folder=tmp_path)
    provider = MarkdownMemoryProviderConfig.from_folder(tmp_path)

    assert len(config.providers) == 1
    assert isinstance(config.providers[0], MarkdownMemoryProviderConfig)
    assert config.providers[0].path_template == str(tmp_path / "{scope}" / "{memory_type}" / "{owner_id}.md")
    assert provider.path_template == config.providers[0].path_template
    assert config.system_sources == ("markdown",)
    assert config.agentic_sources == ("markdown",)
    assert config.write_provider == "markdown"


def test_mem0_memory_config_shortcut_builds_expected_sources() -> None:
    client = object()

    config = MemoryConfig.mem0(client=client)

    assert len(config.providers) == 1
    assert isinstance(config.providers[0], Mem0MemoryProviderConfig)
    assert config.providers[0].client is client
    assert config.system_sources == ("mem0",)
    assert config.agentic_sources == ("mem0",)
    assert config.write_provider == "mem0"


def test_openai_file_search_shortcut_is_retrieval_only() -> None:
    client = _VectorStoreSearchClient()

    config = MemoryConfig.openai_file_search(
        vector_store_ids=["vs_123"],
        scope=MemoryScope.USER,
        owner_attribute_key="memory_owner",
        client=client,
    )

    assert len(config.providers) == 1
    assert isinstance(config.providers[0], OpenAIFileSearchMemoryProviderConfig)
    assert config.providers[0].vector_store_ids == ["vs_123"]
    assert config.providers[0].scope is MemoryScope.USER
    assert config.providers[0].owner_attribute_key == "memory_owner"
    assert config.providers[0].client is client
    assert config.system_sources == ()
    assert config.agentic_sources == ("openai_file_search",)
    assert config.write_provider is None


def test_validate_run_requires_user_id_for_user_scope(markdown_config: MemoryConfig) -> None:
    manager = MemoryManager(markdown_config)
    try:
        with pytest.raises(ValueError, match="user-scoped memory requires"):
            manager.validate_run(
                memory_identity=MemoryIdentity(agency_id="agency-1"),
                agent_name="Support",
                agent_config=AgentMemoryConfig(),
            )
    finally:
        manager.close()


def test_memory_manager_rejects_agentic_only_provider_as_system_source(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot be used as a system memory source"):
        MemoryManager(
            MemoryConfig(
                providers=[
                    OpenAIFileSearchMemoryProviderConfig(
                        vector_store_ids=["vs_123"],
                        client=_VectorStoreSearchClient(),
                    )
                ],
                system_sources=("openai_file_search",),
                agentic_sources=("openai_file_search",),
                write_provider=None,
                journal_path=tmp_path / "jobs.json",
                normalizer=StaticMemoryNormalizer(),
            )
        )


def test_memory_manager_rejects_user_scoped_openai_search_without_owner_attribute_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires owner_attribute_key"):
        MemoryManager(
            MemoryConfig(
                providers=[
                    OpenAIFileSearchMemoryProviderConfig(
                        vector_store_ids=["vs_123"],
                        scope=MemoryScope.USER,
                        client=_VectorStoreSearchClient(),
                    )
                ],
                system_sources=(),
                agentic_sources=("openai_file_search",),
                write_provider=None,
                journal_path=tmp_path / "jobs.json",
                normalizer=StaticMemoryNormalizer(),
            )
        )


def test_agent_memory_config_rejects_search_tool_without_agentic_memory() -> None:
    with pytest.raises(ValueError, match="enable_search_tool requires enable_agentic_memory=True"):
        AgentMemoryConfig(
            enable_agentic_memory=False,
            enable_search_tool=True,
            enable_write_tool=False,
        )


def test_agent_memory_config_rejects_write_tool_without_agentic_memory() -> None:
    with pytest.raises(ValueError, match="enable_write_tool requires enable_agentic_memory=True"):
        AgentMemoryConfig(
            enable_agentic_memory=False,
            enable_search_tool=False,
            enable_write_tool=True,
        )


@pytest.mark.asyncio
async def test_default_permission_resolver_denies_writes(markdown_config: MemoryConfig) -> None:
    manager = MemoryManager(markdown_config)
    request = MemoryWriteRequest(
        operation=MemoryOperation.SAVE,
        content="Remember this",
        rationale="User preference",
        scope=MemoryScope.USER,
        memory_type=MemoryType.SYSTEM,
        source_agent="Support",
        memory_identity=MemoryIdentity(user_id="user-1", agency_id="agency-1"),
        context_snapshot=[],
    )
    try:
        decision = await manager.request_write(
            request=request,
            runtime_context=None,
            agent_config=AgentMemoryConfig(),
        )
        assert decision.mode.value == "deny"
        assert not Path(markdown_config.journal_path).exists()
    finally:
        manager.close()


@pytest.mark.asyncio
async def test_system_memory_recall_orders_scopes(markdown_config: MemoryConfig) -> None:
    manager = MemoryManager(markdown_config)
    identity = MemoryIdentity(user_id="user-1", agency_id="agency-1")
    provider = manager.providers["markdown"]
    try:
        await provider.apply_write(
            write=CanonicalMemoryWrite(
                record_id="agency-memory",
                scope=MemoryScope.AGENCY,
                memory_type=MemoryType.SYSTEM,
                title="Agency memory",
                content="Agency policy",
            ),
            memory_identity=identity,
            agent_name="Support",
        )
        await provider.apply_write(
            write=CanonicalMemoryWrite(
                record_id="agent-memory",
                scope=MemoryScope.AGENT,
                memory_type=MemoryType.SYSTEM,
                title="Agent memory",
                content="Agent preference",
            ),
            memory_identity=identity,
            agent_name="Support",
        )
        await provider.apply_write(
            write=CanonicalMemoryWrite(
                record_id="user-memory",
                scope=MemoryScope.USER,
                memory_type=MemoryType.SYSTEM,
                title="User memory",
                content="User prefers concise answers",
            ),
            memory_identity=identity,
            agent_name="Support",
        )

        memory_block = await manager.build_system_memory(
            memory_identity=identity,
            agent_name="Support",
            agent_config=AgentMemoryConfig(),
        )
        assert memory_block is not None
        assert memory_block.index("Agency policy") < memory_block.index("Agent preference")
        assert memory_block.index("Agent preference") < memory_block.index("User prefers concise answers")
    finally:
        manager.close()


@pytest.mark.asyncio
async def test_openai_file_search_provider_serves_agentic_search(tmp_path: Path) -> None:
    client = _VectorStoreSearchClient()
    manager = MemoryManager(
        MemoryConfig(
            providers=[
                OpenAIFileSearchMemoryProviderConfig(
                    vector_store_ids=["vs_123"],
                    scope=MemoryScope.USER,
                    owner_attribute_key="memory_owner",
                    client=client,
                )
            ],
            system_sources=(),
            agentic_sources=("openai_file_search",),
            write_provider=None,
            journal_path=tmp_path / "jobs.json",
            normalizer=StaticMemoryNormalizer(),
        )
    )
    try:
        results = await manager.search_memory(
            query="pricing",
            memory_identity=MemoryIdentity(user_id="user-1", agency_id="agency-1"),
            agent_name="Support",
            agent_config=AgentMemoryConfig(
                enable_system_memory=False,
                allowed_scopes=(MemoryScope.USER,),
            ),
        )
        assert len(results) == 1
        assert results[0].content == "match for pricing"
        assert results[0].provider_name == "openai_file_search"
        assert results[0].scope is MemoryScope.USER
        assert results[0].owner_id == "user-1"
        assert client.calls == [
            {
                "vector_store_id": "vs_123",
                "query": "pricing",
                "filters": {"type": "eq", "key": "memory_owner", "value": "user-1"},
                "max_num_results": 5,
            }
        ]
    finally:
        manager.close()


@pytest.mark.asyncio
async def test_search_memory_rejects_unknown_provider(markdown_config: MemoryConfig) -> None:
    manager = MemoryManager(markdown_config)
    try:
        with pytest.raises(ValueError, match="Unknown memory provider 'bogus'"):
            await manager.search_memory(
                query="pricing",
                memory_identity=MemoryIdentity(agency_id="agency-1"),
                agent_name="Support",
                agent_config=AgentMemoryConfig(allowed_scopes=(MemoryScope.AGENCY,)),
                providers=["bogus"],
            )
    finally:
        manager.close()


@pytest.mark.asyncio
async def test_request_write_rejects_unknown_provider(tmp_path: Path) -> None:
    async def allow_all(*_args, **_kwargs):
        return MemoryPermissionDecision.allow()

    manager = MemoryManager(
        MemoryConfig.markdown(
            folder=tmp_path,
            journal_path=tmp_path / "jobs.json",
            normalizer=StaticMemoryNormalizer(),
            permission_resolver=allow_all,
        )
    )
    try:
        with pytest.raises(ValueError, match="Unknown memory provider 'bogus'"):
            await manager.request_write(
                request=MemoryWriteRequest(
                    operation=MemoryOperation.SAVE,
                    content="remember this",
                    rationale="preference",
                    scope=MemoryScope.AGENCY,
                    memory_type=MemoryType.SYSTEM,
                    source_agent="Support",
                    memory_identity=MemoryIdentity(agency_id="agency-1"),
                    context_snapshot=[],
                    requested_providers=["bogus"],
                ),
                runtime_context=None,
                agent_config=AgentMemoryConfig(allowed_scopes=(MemoryScope.AGENCY,)),
            )
        assert not (tmp_path / "jobs.json").exists()
    finally:
        manager.close()


@pytest.mark.asyncio
async def test_openai_file_search_provider_skips_other_scopes(tmp_path: Path) -> None:
    manager = MemoryManager(
        MemoryConfig(
            providers=[
                OpenAIFileSearchMemoryProviderConfig(
                    vector_store_ids=["vs_123"],
                    scope=MemoryScope.USER,
                    owner_attribute_key="memory_owner",
                    client=_VectorStoreSearchClient(),
                )
            ],
            system_sources=(),
            agentic_sources=("openai_file_search",),
            write_provider=None,
            journal_path=tmp_path / "jobs.json",
            normalizer=StaticMemoryNormalizer(),
        )
    )
    try:
        results = await manager.search_memory(
            query="pricing",
            memory_identity=MemoryIdentity(user_id="user-1", agency_id="agency-1"),
            agent_name="Support",
            agent_config=AgentMemoryConfig(
                enable_system_memory=False,
                allowed_scopes=(MemoryScope.AGENT,),
            ),
        )
        assert results == []
    finally:
        manager.close()


def test_sync_caller_can_enqueue_memory_write(markdown_config: MemoryConfig) -> None:
    async def allow_all(*_args, **_kwargs):
        return MemoryPermissionDecision.allow()

    markdown_config.permission_resolver = allow_all
    manager = MemoryManager(markdown_config)
    request = MemoryWriteRequest(
        operation=MemoryOperation.SAVE,
        content="Customer likes weekly reports",
        rationale="Useful preference",
        scope=MemoryScope.USER,
        memory_type=MemoryType.SYSTEM,
        source_agent="Support",
        memory_identity=MemoryIdentity(user_id="user-1", agency_id="agency-1"),
        context_snapshot=[{"role": "user", "content": "Send weekly reports."}],
    )
    target_path = Path(
        markdown_config.providers[0].path_template.format(
            scope="user",
            memory_type="system",
            owner_id="user-1",
        )
    )

    try:
        decision = asyncio.run(
            manager.request_write(
                request=request,
                runtime_context=None,
                agent_config=AgentMemoryConfig(),
            )
        )
        assert decision.mode.value == "allow"

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if target_path.exists() and "Customer likes weekly reports" in target_path.read_text(encoding="utf-8"):
                break
            time.sleep(0.05)
        else:
            pytest.fail("memory write was not persisted from sync caller")
        file_text = target_path.read_text(encoding="utf-8")
        assert file_text.startswith("# Durable Memory")
    finally:
        manager.close()
