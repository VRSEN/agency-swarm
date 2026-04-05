from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import (
    AgentMemoryConfig,
    MarkdownMemoryProviderConfig,
    Mem0MemoryProviderConfig,
    MemoryConfig,
    OpenAIFileSearchMemoryProviderConfig,
)
from .provider import MemoryProvider
from .providers.markdown import MarkdownMemoryProvider
from .providers.mem0 import Mem0MemoryProvider
from .providers.openai_file_search import OpenAIFileSearchMemoryProvider
from .queue import DurableMemoryQueue
from .types import (
    MemoryIdentity,
    MemoryOperation,
    MemoryPermissionDecision,
    MemoryPermissionMode,
    MemoryProviderCapabilities,
    MemoryRecord,
    MemoryScope,
    MemoryType,
    MemoryWriteJob,
    MemoryWriteRequest,
)

if TYPE_CHECKING:
    from agency_swarm.context import MasterContext


class MemoryManager:
    def __init__(self, config: MemoryConfig):
        self.config = config
        self.providers = self._build_providers(config.providers)
        self._validate_config()
        journal_path = Path(config.journal_path or ".agency_swarm/memory/jobs.json")
        self.queue = DurableMemoryQueue(journal_path=journal_path, manager=self)

    def close(self) -> None:
        self.queue.close()

    def validate_run(
        self,
        *,
        memory_identity: MemoryIdentity | None,
        agent_name: str,
        agent_config: AgentMemoryConfig | None,
    ) -> None:
        if memory_identity is None or agent_config is None:
            return

        enabled_scopes: set[MemoryScope] = set()
        if agent_config.enable_system_memory or agent_config.enable_agentic_memory:
            enabled_scopes.update(agent_config.allowed_scopes)
        if agent_config.enable_search_tool:
            enabled_scopes.update(agent_config.allowed_scopes)
        if agent_config.enable_write_tool:
            enabled_scopes.update(agent_config.allowed_scopes)

        for scope in enabled_scopes:
            memory_identity.resolve_scope_owner(scope, agent_name=agent_name)

    async def build_system_memory(
        self,
        *,
        memory_identity: MemoryIdentity | None,
        agent_name: str,
        agent_config: AgentMemoryConfig | None,
    ) -> str | None:
        if not memory_identity or not agent_config or not agent_config.enable_system_memory:
            return None
        scopes = self._resolve_scopes(agent_config.allowed_scopes)
        records = await self._recall_system_records(
            memory_identity=memory_identity,
            agent_name=agent_name,
            scopes=scopes,
        )
        if not records:
            return None
        lines: list[str] = []
        remaining = self.config.system_budget_chars
        for record in records:
            line = f"- [{record.scope.value}/{record.provider_name}] {record.content.strip()}"
            if not line.strip():
                continue
            if len(line) > remaining:
                line = line[:remaining].rstrip()
            if not line:
                break
            lines.append(line)
            remaining -= len(line) + 1
            if remaining <= 0:
                break
        if not lines:
            return None
        return "Durable memory:\n" + "\n".join(lines)

    async def search_memory(
        self,
        *,
        query: str,
        memory_identity: MemoryIdentity | None,
        agent_name: str,
        agent_config: AgentMemoryConfig | None,
        scopes: tuple[MemoryScope, ...] | None = None,
        providers: list[str] | None = None,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        if not memory_identity:
            return []
        if agent_config and not agent_config.enable_agentic_memory:
            return []
        resolved_scopes = scopes or self._resolve_scopes(
            agent_config.allowed_scopes if agent_config else tuple(MemoryScope)
        )
        provider_names = providers or list(self.config.agentic_sources)
        results: list[MemoryRecord] = []
        for provider_name in provider_names:
            provider = self.providers[provider_name]
            if not provider.capabilities.agentic_search:
                continue
            provider_results = await provider.search_agentic(
                query=query,
                memory_identity=memory_identity,
                agent_name=agent_name,
                scopes=resolved_scopes,
                limit=limit or self.config.search_result_limit,
            )
            results.extend(provider_results)
        deduped = self._dedupe_records(results)
        return deduped[: limit or self.config.search_result_limit]

    async def request_write(
        self,
        *,
        request: MemoryWriteRequest,
        runtime_context: MasterContext | None,
        agent_config: AgentMemoryConfig | None,
    ) -> MemoryPermissionDecision:
        if agent_config and request.scope not in agent_config.allowed_scopes:
            return MemoryPermissionDecision.deny()
        decision = await _maybe_await(
            self.config.permission_resolver(request, request.memory_identity, runtime_context)
        )
        if decision.mode is not MemoryPermissionMode.ALLOW:
            return decision
        if not decision.allows_scope(request.scope) or not decision.allows_type(request.memory_type):
            return MemoryPermissionDecision.deny()
        provider_names = request.requested_providers or (
            [self.config.write_provider] if self.config.write_provider else []
        )
        resolved_provider_names = [name for name in provider_names if decision.allows_provider(name)]
        if not resolved_provider_names:
            return MemoryPermissionDecision.deny()
        job = MemoryWriteJob(
            job_id=self.queue.new_job_id(),
            request=request,
            provider_names=resolved_provider_names,
        )
        self.queue.enqueue(job)
        return decision

    async def process_job(self, job: MemoryWriteJob) -> None:
        if job.request.operation is MemoryOperation.DELETE:
            if not job.request.record_id:
                raise ValueError("delete operations require record_id")
            for provider_name in job.provider_names:
                provider = self.providers[provider_name]
                if not provider.capabilities.delete:
                    raise ValueError(f"Provider '{provider_name}' does not support deletes")
                await provider.delete_record(
                    record_id=job.request.record_id,
                    memory_identity=job.request.memory_identity,
                    agent_name=job.request.source_agent,
                )
            return

        provider_names = job.provider_names
        existing_records = await self._load_existing_records(
            memory_identity=job.request.memory_identity,
            agent_name=job.request.source_agent,
            scope=job.request.scope,
            memory_type=job.request.memory_type,
            provider_names=provider_names,
        )
        canonical_write = await self.config.normalizer.normalize(
            request=job.request,
            existing_records=existing_records,
            model=self.config.writer_model,
        )
        for provider_name in provider_names:
            provider = self.providers[provider_name]
            if not provider.capabilities.write:
                raise ValueError(f"Provider '{provider_name}' does not support writes")
            await provider.apply_write(
                write=canonical_write,
                memory_identity=job.request.memory_identity,
                agent_name=job.request.source_agent,
            )

    def _build_providers(
        self,
        configs: list[MarkdownMemoryProviderConfig | Mem0MemoryProviderConfig | OpenAIFileSearchMemoryProviderConfig],
    ) -> dict[str, MemoryProvider]:
        providers: dict[str, MemoryProvider] = {}
        for provider_config in configs:
            provider: MemoryProvider
            if isinstance(provider_config, MarkdownMemoryProviderConfig):
                provider = MarkdownMemoryProvider(
                    name=provider_config.name,
                    path_template=provider_config.path_template,
                )
            elif isinstance(provider_config, Mem0MemoryProviderConfig):
                provider = Mem0MemoryProvider(name=provider_config.name, client=provider_config.client)
            elif isinstance(provider_config, OpenAIFileSearchMemoryProviderConfig):
                provider = OpenAIFileSearchMemoryProvider(
                    name=provider_config.name,
                    vector_store_ids=provider_config.vector_store_ids,
                    scope=provider_config.scope,
                    client=provider_config.client,
                )
            else:
                raise TypeError(f"Unsupported memory provider config: {type(provider_config)}")
            providers[provider.name] = provider
        return providers

    def _validate_config(self) -> None:
        for source_name in self.config.system_sources:
            capabilities = self._provider_capabilities(source_name)
            if not capabilities.system_recall:
                raise ValueError(f"Memory provider '{source_name}' cannot be used as a system memory source")
        for source_name in self.config.agentic_sources:
            capabilities = self._provider_capabilities(source_name)
            if not capabilities.agentic_search:
                raise ValueError(f"Memory provider '{source_name}' cannot be used as an agentic memory source")
        if self.config.write_provider:
            capabilities = self._provider_capabilities(self.config.write_provider)
            if not capabilities.write:
                raise ValueError(f"Memory provider '{self.config.write_provider}' cannot be used as a write provider")

    def _provider_capabilities(self, provider_name: str) -> MemoryProviderCapabilities:
        if provider_name not in self.providers:
            raise ValueError(f"Unknown memory provider '{provider_name}'")
        return self.providers[provider_name].capabilities

    def _resolve_scopes(self, scopes: tuple[MemoryScope, ...]) -> tuple[MemoryScope, ...]:
        ordered: list[MemoryScope] = []
        for scope in (MemoryScope.AGENCY, MemoryScope.AGENT, MemoryScope.USER):
            if scope in scopes:
                ordered.append(scope)
        return tuple(ordered)

    async def _recall_system_records(
        self,
        *,
        memory_identity: MemoryIdentity,
        agent_name: str,
        scopes: tuple[MemoryScope, ...],
    ) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        for provider_name in self.config.system_sources:
            provider = self.providers[provider_name]
            provider_records = await provider.recall_system(
                memory_identity=memory_identity,
                agent_name=agent_name,
                scopes=scopes,
                limit=self.config.search_result_limit,
            )
            records.extend(provider_records)
        return self._dedupe_records(records)

    async def _load_existing_records(
        self,
        *,
        memory_identity: MemoryIdentity,
        agent_name: str,
        scope: MemoryScope,
        memory_type: MemoryType,
        provider_names: list[str],
    ) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        for provider_name in provider_names:
            provider = self.providers[provider_name]
            if memory_type is MemoryType.SYSTEM and provider.capabilities.system_recall:
                records.extend(
                    await provider.recall_system(
                        memory_identity=memory_identity,
                        agent_name=agent_name,
                        scopes=(scope,),
                        limit=self.config.search_result_limit,
                    )
                )
            elif memory_type is MemoryType.AGENTIC and provider.capabilities.agentic_search:
                records.extend(
                    await provider.search_agentic(
                        query="",
                        memory_identity=memory_identity,
                        agent_name=agent_name,
                        scopes=(scope,),
                        limit=self.config.search_result_limit,
                    )
                )
        return self._dedupe_records(records)

    def _dedupe_records(self, records: list[MemoryRecord]) -> list[MemoryRecord]:
        seen: set[tuple[str, str]] = set()
        deduped: list[MemoryRecord] = []
        for record in records:
            key = (record.provider_name, record.record_id)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(record)
        return deduped


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value):
        return await value
    return value
