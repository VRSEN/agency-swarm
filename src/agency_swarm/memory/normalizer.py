from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from typing import Any

from agents import Agent as SDKAgent, ModelSettings, Runner

from .types import CanonicalMemoryWrite, MemoryOperation, MemoryRecord, MemoryWriteRequest


class MemoryNormalizer(ABC):
    @abstractmethod
    async def normalize(
        self,
        *,
        request: MemoryWriteRequest,
        existing_records: list[MemoryRecord],
        model: Any | None = None,
    ) -> CanonicalMemoryWrite:
        raise NotImplementedError


class LLMMemoryNormalizer(MemoryNormalizer):
    async def normalize(
        self,
        *,
        request: MemoryWriteRequest,
        existing_records: list[MemoryRecord],
        model: Any | None = None,
    ) -> CanonicalMemoryWrite:
        if request.operation is MemoryOperation.DELETE:
            if not request.record_id:
                raise ValueError("delete operations require record_id")
            return CanonicalMemoryWrite(
                record_id=request.record_id,
                scope=request.scope,
                memory_type=request.memory_type,
                title=request.title or "Deleted memory",
                content="",
            )

        agent = SDKAgent(
            name="MemoryWriter",
            instructions=(
                "You normalize durable memory writes. "
                "You must produce a concise title and a clean memory body. "
                "Do not include markdown headings. "
                "Avoid duplicates, merge obvious overlap, and keep only stable facts or instructions."
            ),
            output_type=CanonicalMemoryWrite,
            model=model,
            model_settings=ModelSettings(temperature=0),
        )
        existing_payload = [
            {
                "record_id": record.record_id,
                "title": record.title,
                "content": record.content,
                "scope": record.scope.value,
                "memory_type": record.memory_type.value,
            }
            for record in existing_records
        ]
        prompt = json.dumps(
            {
                "request": {
                    "content": request.content,
                    "rationale": request.rationale,
                    "scope": request.scope.value,
                    "memory_type": request.memory_type.value,
                    "title": request.title,
                },
                "existing_records": existing_payload,
                "context_snapshot": request.context_snapshot,
            },
            ensure_ascii=True,
        )
        result = await Runner.run(agent, prompt)
        output = result.final_output
        if not isinstance(output, CanonicalMemoryWrite):
            raise TypeError("Memory normalizer must return CanonicalMemoryWrite")
        if not output.record_id:
            output.record_id = _build_record_id(request.scope.value, request.memory_type.value, output.content)
        output.scope = request.scope
        output.memory_type = request.memory_type
        return output


def _build_record_id(scope: str, memory_type: str, content: str) -> str:
    digest = hashlib.sha1(f"{scope}:{memory_type}:{content}".encode()).hexdigest()
    return f"mem_{digest[:16]}"
