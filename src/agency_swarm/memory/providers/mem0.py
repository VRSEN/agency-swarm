from __future__ import annotations

import importlib
from typing import Any

from agency_swarm.memory.provider import MemoryProvider
from agency_swarm.memory.types import (
    CanonicalMemoryWrite,
    MemoryIdentity,
    MemoryProviderCapabilities,
    MemoryRecord,
    MemoryScope,
    MemoryType,
)


class Mem0MemoryProvider(MemoryProvider):
    def __init__(self, *, name: str, client: Any | None = None):
        self.name = name
        self.client = client or _build_default_client()
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
        records: list[MemoryRecord] = []
        for scope in scopes:
            filters = _build_filters(scope, memory_identity, agent_name=agent_name)
            payload = await self.client.search(query="system memory", filters=filters, limit=limit)
            records.extend(
                _convert_search_results(
                    payload,
                    provider_name=self.name,
                    scope=scope,
                    memory_type=MemoryType.SYSTEM,
                    owner_id=memory_identity.resolve_scope_owner(scope, agent_name=agent_name),
                )
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
        records: list[MemoryRecord] = []
        for scope in scopes:
            filters = _build_filters(scope, memory_identity, agent_name=agent_name)
            payload = await self.client.search(query=query, filters=filters, limit=limit)
            records.extend(
                _convert_search_results(
                    payload,
                    provider_name=self.name,
                    scope=scope,
                    memory_type=MemoryType.AGENTIC,
                    owner_id=memory_identity.resolve_scope_owner(scope, agent_name=agent_name),
                )
            )
        return records[:limit]

    async def apply_write(
        self,
        *,
        write: CanonicalMemoryWrite,
        memory_identity: MemoryIdentity,
        agent_name: str,
    ) -> MemoryRecord:
        owner_id = memory_identity.resolve_scope_owner(write.scope, agent_name=agent_name)
        payload = await self.client.add(
            messages=[{"role": "system", "content": write.content}],
            user_id=owner_id if write.scope is MemoryScope.USER else None,
            agent_id=agent_name if write.scope is MemoryScope.AGENT else None,
            metadata={
                "agency_id": memory_identity.agency_id,
                "scope": write.scope.value,
                "memory_type": write.memory_type.value,
                "record_id": write.record_id,
                "title": write.title,
                **write.metadata,
            },
        )
        result_id = getattr(payload, "id", None) or write.record_id
        return MemoryRecord(
            record_id=result_id,
            provider_name=self.name,
            scope=write.scope,
            memory_type=write.memory_type,
            owner_id=owner_id,
            title=write.title,
            content=write.content,
            metadata=write.metadata,
        )

    async def delete_record(self, *, record_id: str, memory_identity: MemoryIdentity, agent_name: str) -> None:
        await self.client.delete(memory_id=record_id)


def _build_default_client() -> Any:
    module = importlib.import_module("mem0")
    client_cls = getattr(module, "MemoryClient", None) or getattr(module, "Memory", None)
    if client_cls is None:
        raise ImportError("Mem0 provider requires the mem0 SDK to be installed")
    return client_cls()


def _build_filters(scope: MemoryScope, memory_identity: MemoryIdentity, *, agent_name: str) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if scope is MemoryScope.USER:
        if not memory_identity.user_id:
            raise ValueError("user-scoped memory requires memory_identity.user_id")
        filters["user_id"] = memory_identity.user_id
    elif scope is MemoryScope.AGENT:
        filters["agent_id"] = agent_name
    else:
        if not memory_identity.agency_id:
            raise ValueError("agency-scoped memory requires memory_identity.agency_id")
        filters["metadata"] = {"agency_id": memory_identity.agency_id}
    return filters


def _convert_search_results(
    payload: Any,
    *,
    provider_name: str,
    scope: MemoryScope,
    memory_type: MemoryType,
    owner_id: str,
) -> list[MemoryRecord]:
    records: list[MemoryRecord] = []
    iterable = getattr(payload, "results", None) or payload
    for item in iterable:
        item_id = getattr(item, "id", None) or item.get("id")
        memory = getattr(item, "memory", None) or item.get("memory")
        metadata = getattr(item, "metadata", None) or item.get("metadata") or {}
        records.append(
            MemoryRecord(
                record_id=item_id,
                provider_name=provider_name,
                scope=scope,
                memory_type=memory_type,
                owner_id=owner_id,
                title=metadata.get("title"),
                content=memory,
                metadata=metadata,
            )
        )
    return records
