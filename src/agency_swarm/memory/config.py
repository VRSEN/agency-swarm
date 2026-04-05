from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict, Unpack

from .normalizer import LLMMemoryNormalizer, MemoryNormalizer
from .types import MemoryPermissionDecision, MemoryScope

if TYPE_CHECKING:
    from agency_swarm.context import MasterContext

    from .types import MemoryIdentity, MemoryWriteRequest

MemoryPermissionResolver = Callable[
    ["MemoryWriteRequest", "MemoryIdentity", "MasterContext | None"],
    Awaitable[MemoryPermissionDecision] | MemoryPermissionDecision,
]
DEFAULT_MARKDOWN_MEMORY_FOLDER = ".agency_swarm/memory"
DEFAULT_MARKDOWN_MEMORY_PATH = ".agency_swarm/memory/{scope}/{memory_type}/{owner_id}.md"


class MemoryConfigOptions(TypedDict, total=False):
    agency_id: str | None
    journal_path: str | Path | None
    system_budget_chars: int
    search_result_limit: int
    recent_message_limit: int
    writer_model: Any | None
    normalizer: MemoryNormalizer
    permission_resolver: MemoryPermissionResolver


def build_markdown_path_template(folder: str | os.PathLike[str]) -> str:
    """Map a memory root folder to the internal markdown file layout."""
    return str(Path(folder) / "{scope}" / "{memory_type}" / "{owner_id}.md")


@dataclass(slots=True)
class AgentMemoryConfig:
    enable_system_memory: bool = True
    enable_agentic_memory: bool = True
    enable_search_tool: bool = True
    enable_write_tool: bool = True
    allowed_scopes: tuple[MemoryScope, ...] = (
        MemoryScope.AGENCY,
        MemoryScope.AGENT,
        MemoryScope.USER,
    )


@dataclass(slots=True)
class MarkdownMemoryProviderConfig:
    name: str = "markdown"
    path_template: str = DEFAULT_MARKDOWN_MEMORY_PATH

    @classmethod
    def from_folder(cls, folder: str | os.PathLike[str]) -> MarkdownMemoryProviderConfig:
        """Build a markdown provider from a simple root folder."""
        return cls(path_template=build_markdown_path_template(folder))


@dataclass(slots=True)
class Mem0MemoryProviderConfig:
    name: str = "mem0"
    client: Any | None = None


@dataclass(slots=True)
class OpenAIFileSearchMemoryProviderConfig:
    name: str = "openai_file_search"
    vector_store_ids: list[str] = field(default_factory=list)
    scope: MemoryScope = MemoryScope.AGENT
    client: Any | None = None


MemoryProviderConfig = MarkdownMemoryProviderConfig | Mem0MemoryProviderConfig | OpenAIFileSearchMemoryProviderConfig


@dataclass(slots=True)
class MemoryConfig:
    providers: list[MemoryProviderConfig] = field(default_factory=lambda: [MarkdownMemoryProviderConfig()])
    agency_id: str | None = None
    system_sources: tuple[str, ...] = ("markdown",)
    agentic_sources: tuple[str, ...] = ("markdown",)
    write_provider: str | None = "markdown"
    journal_path: str | Path | None = None
    system_budget_chars: int = 2000
    search_result_limit: int = 5
    recent_message_limit: int = 8
    writer_model: Any | None = None
    normalizer: MemoryNormalizer = field(default_factory=LLMMemoryNormalizer)
    permission_resolver: MemoryPermissionResolver = field(default_factory=lambda: deny_by_default)

    @classmethod
    def markdown(
        cls,
        *,
        folder: str | os.PathLike[str] = DEFAULT_MARKDOWN_MEMORY_FOLDER,
        path_template: str | None = None,
        **options: Unpack[MemoryConfigOptions],
    ) -> MemoryConfig:
        """Build the common markdown-backed memory setup."""
        effective_path_template = path_template or build_markdown_path_template(folder)
        return cls(
            providers=[MarkdownMemoryProviderConfig(path_template=effective_path_template)],
            system_sources=("markdown",),
            agentic_sources=("markdown",),
            write_provider="markdown",
            **options,
        )

    @classmethod
    def mem0(
        cls,
        *,
        client: Any | None = None,
        **options: Unpack[MemoryConfigOptions],
    ) -> MemoryConfig:
        """Build a Mem0-backed memory setup."""
        return cls(
            providers=[Mem0MemoryProviderConfig(client=client)],
            system_sources=("mem0",),
            agentic_sources=("mem0",),
            write_provider="mem0",
            **options,
        )

    @classmethod
    def openai_file_search(
        cls,
        *,
        vector_store_ids: list[str],
        scope: MemoryScope = MemoryScope.AGENT,
        client: Any | None = None,
        **options: Unpack[MemoryConfigOptions],
    ) -> MemoryConfig:
        """Build a retrieval-only OpenAI file search memory setup."""
        return cls(
            providers=[
                OpenAIFileSearchMemoryProviderConfig(
                    vector_store_ids=vector_store_ids,
                    scope=scope,
                    client=client,
                )
            ],
            system_sources=(),
            agentic_sources=("openai_file_search",),
            write_provider=None,
            **options,
        )


async def deny_by_default(*_args: Any, **_kwargs: Any) -> MemoryPermissionDecision:
    return MemoryPermissionDecision.deny()


Memory = MemoryConfig
