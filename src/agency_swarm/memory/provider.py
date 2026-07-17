from __future__ import annotations

from abc import ABC, abstractmethod

from .types import CanonicalMemoryWrite, MemoryIdentity, MemoryProviderCapabilities, MemoryRecord, MemoryScope


class MemoryProvider(ABC):
    name: str
    capabilities: MemoryProviderCapabilities

    @abstractmethod
    async def recall_system(
        self,
        *,
        memory_identity: MemoryIdentity,
        agent_name: str,
        scopes: tuple[MemoryScope, ...],
        limit: int,
    ) -> list[MemoryRecord]:
        raise NotImplementedError

    @abstractmethod
    async def search_agentic(
        self,
        *,
        query: str,
        memory_identity: MemoryIdentity,
        agent_name: str,
        scopes: tuple[MemoryScope, ...],
        limit: int,
    ) -> list[MemoryRecord]:
        raise NotImplementedError

    @abstractmethod
    async def apply_write(
        self,
        *,
        write: CanonicalMemoryWrite,
        memory_identity: MemoryIdentity,
        agent_name: str,
    ) -> MemoryRecord:
        raise NotImplementedError

    @abstractmethod
    async def delete_record(self, *, record_id: str, memory_identity: MemoryIdentity, agent_name: str) -> None:
        raise NotImplementedError
