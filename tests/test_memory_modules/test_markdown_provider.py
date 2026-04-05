from pathlib import Path

import pytest

from agency_swarm.memory.providers.markdown import MarkdownMemoryProvider
from agency_swarm.memory.types import CanonicalMemoryWrite, MemoryIdentity, MemoryScope, MemoryType


@pytest.mark.asyncio
async def test_markdown_provider_escapes_record_delimiters_in_content(tmp_path: Path) -> None:
    provider = MarkdownMemoryProvider(
        name="markdown",
        path_template=str(tmp_path / "{scope}" / "{memory_type}" / "{owner_id}.md"),
    )
    original_content = (
        "Keep this exact text.\n<!-- memory-record-start -->\nStill part of the memory.\n<!-- memory-record-end -->"
    )

    record = await provider.apply_write(
        write=CanonicalMemoryWrite(
            record_id="mem_1",
            scope=MemoryScope.USER,
            memory_type=MemoryType.SYSTEM,
            title="Delimiter safety",
            content=original_content,
        ),
        memory_identity=MemoryIdentity(user_id="user-1"),
        agent_name="Support",
    )

    stored_path = tmp_path / "user" / "system" / "user-1.md"
    stored_text = stored_path.read_text(encoding="utf-8")
    recalled = await provider.recall_system(
        memory_identity=MemoryIdentity(user_id="user-1"),
        agent_name="Support",
        scopes=(MemoryScope.USER,),
        limit=5,
    )

    assert record.content == original_content
    assert stored_text.count("<!-- memory-record-end -->") == 1
    assert "&lt;!-- memory-record-start --&gt;" in stored_text
    assert "&lt;!-- memory-record-end --&gt;" in stored_text
    assert [memory.content for memory in recalled] == [original_content]
