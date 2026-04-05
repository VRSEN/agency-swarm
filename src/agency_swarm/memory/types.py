from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MemoryScope(StrEnum):
    USER = "user"
    AGENT = "agent"
    AGENCY = "agency"


class MemoryType(StrEnum):
    SYSTEM = "system"
    AGENTIC = "agentic"


class MemoryOperation(StrEnum):
    SAVE = "save"
    DELETE = "delete"


class MemoryPermissionMode(StrEnum):
    DENY = "deny"
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"


@dataclass(slots=True)
class MemoryIdentity:
    user_id: str | None = None
    agency_id: str | None = None
    session_id: str | None = None

    def resolve_scope_owner(self, scope: MemoryScope, *, agent_name: str) -> str:
        if scope is MemoryScope.USER:
            if not self.user_id:
                raise ValueError("user-scoped memory requires memory_identity.user_id")
            return self.user_id
        if scope is MemoryScope.AGENCY:
            if not self.agency_id:
                raise ValueError("agency-scoped memory requires memory_identity.agency_id")
            return self.agency_id
        return agent_name


@dataclass(slots=True)
class MemoryProviderCapabilities:
    system_recall: bool = False
    agentic_search: bool = False
    write: bool = False
    delete: bool = False
    supported_scopes: tuple[MemoryScope, ...] = (
        MemoryScope.AGENCY,
        MemoryScope.AGENT,
        MemoryScope.USER,
    )


@dataclass(slots=True)
class MemoryPermissionDecision:
    mode: MemoryPermissionMode
    allowed_scopes: set[MemoryScope] | None = None
    allowed_types: set[MemoryType] | None = None
    allowed_providers: set[str] | None = None

    @classmethod
    def deny(cls) -> MemoryPermissionDecision:
        return cls(mode=MemoryPermissionMode.DENY)

    @classmethod
    def allow(
        cls,
        *,
        scopes: set[MemoryScope] | None = None,
        types: set[MemoryType] | None = None,
        providers: set[str] | None = None,
    ) -> MemoryPermissionDecision:
        return cls(
            mode=MemoryPermissionMode.ALLOW,
            allowed_scopes=scopes,
            allowed_types=types,
            allowed_providers=providers,
        )

    @classmethod
    def require_approval(cls) -> MemoryPermissionDecision:
        return cls(mode=MemoryPermissionMode.REQUIRE_APPROVAL)

    def allows_scope(self, scope: MemoryScope) -> bool:
        return self.allowed_scopes is None or scope in self.allowed_scopes

    def allows_type(self, memory_type: MemoryType) -> bool:
        return self.allowed_types is None or memory_type in self.allowed_types

    def allows_provider(self, provider_name: str) -> bool:
        return self.allowed_providers is None or provider_name in self.allowed_providers


@dataclass(slots=True)
class MemoryRecord:
    record_id: str
    provider_name: str
    scope: MemoryScope
    memory_type: MemoryType
    owner_id: str
    content: str
    title: str | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MemoryWriteRequest:
    operation: MemoryOperation
    content: str
    rationale: str
    scope: MemoryScope
    memory_type: MemoryType
    source_agent: str
    memory_identity: MemoryIdentity
    context_snapshot: list[dict[str, Any]]
    requested_providers: list[str] | None = None
    record_id: str | None = None
    title: str | None = None


@dataclass(slots=True)
class CanonicalMemoryWrite:
    record_id: str
    scope: MemoryScope
    memory_type: MemoryType
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MemoryWriteJob:
    job_id: str
    request: MemoryWriteRequest
    provider_names: list[str]
    status: str = "queued"
    attempts: int = 0
    error: str | None = None
