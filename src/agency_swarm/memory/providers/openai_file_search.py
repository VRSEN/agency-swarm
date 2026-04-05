from __future__ import annotations

from openai import AsyncOpenAI

from agency_swarm.memory.provider import MemoryProvider
from agency_swarm.memory.types import (
    CanonicalMemoryWrite,
    MemoryIdentity,
    MemoryProviderCapabilities,
    MemoryRecord,
    MemoryScope,
    MemoryType,
)


class OpenAIFileSearchMemoryProvider(MemoryProvider):
    def __init__(
        self,
        *,
        name: str,
        vector_store_ids: list[str],
        scope: MemoryScope = MemoryScope.AGENT,
        client: AsyncOpenAI | None = None,
    ):
        if not vector_store_ids:
            raise ValueError("OpenAIFileSearchMemoryProvider requires at least one vector_store_id")
        self.name = name
        self.vector_store_ids = list(vector_store_ids)
        self.scope = scope
        self.client = client or AsyncOpenAI()
        self.capabilities = MemoryProviderCapabilities(
            system_recall=False,
            agentic_search=True,
            write=False,
            delete=False,
            supported_scopes=(scope,),
        )

    async def recall_system(
        self,
        *,
        memory_identity: MemoryIdentity,
        agent_name: str,
        scopes: tuple[MemoryScope, ...],
        limit: int,
    ) -> list[MemoryRecord]:
        raise ValueError("OpenAI file search memory provider does not support system recall")

    async def search_agentic(
        self,
        *,
        query: str,
        memory_identity: MemoryIdentity,
        agent_name: str,
        scopes: tuple[MemoryScope, ...],
        limit: int,
    ) -> list[MemoryRecord]:
        if self.scope not in scopes:
            return []

        owner_id = memory_identity.resolve_scope_owner(self.scope, agent_name=agent_name)
        results: list[MemoryRecord] = []
        for vector_store_id in self.vector_store_ids:
            page = await self.client.vector_stores.search(
                vector_store_id=vector_store_id,
                query=query,
                max_num_results=limit,
            )
            for item in page.data:
                content_text = "\n".join(result.text or "" for result in getattr(item, "content", []))
                results.append(
                    MemoryRecord(
                        record_id=getattr(item, "file_id", vector_store_id),
                        provider_name=self.name,
                        scope=self.scope,
                        memory_type=MemoryType.AGENTIC,
                        owner_id=owner_id,
                        content=content_text,
                        title=getattr(item, "filename", None),
                    )
                )
        return results[:limit]

    async def apply_write(
        self,
        *,
        write: CanonicalMemoryWrite,
        memory_identity: MemoryIdentity,
        agent_name: str,
    ) -> MemoryRecord:
        raise ValueError("OpenAI file search memory provider is read-only")

    async def delete_record(self, *, record_id: str, memory_identity: MemoryIdentity, agent_name: str) -> None:
        raise ValueError("OpenAI file search memory provider is read-only")
