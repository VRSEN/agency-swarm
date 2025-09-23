import pytest

from agency_swarm.ui.demos.compact import compact_thread
from agency_swarm.utils.thread import ThreadManager


class _Agency:
    def __init__(self, entry_points):
        self.entry_points = entry_points
        self.thread_manager = ThreadManager()


"""Edge-case tests for compact_thread.

This file intentionally avoids mocking the OpenAI client to non-Response
types. In production, compact_thread receives an OpenAI Response object.
"""


@pytest.mark.asyncio
async def test_compact_thread_requires_entry_points(monkeypatch):
    # Avoid touching TerminalDemoLauncher; function raises early when no entry points
    agency = _Agency(entry_points=[])
    with pytest.raises(RuntimeError) as ei:
        await compact_thread(agency, [])
    assert "Agency has no entry points" in str(ei.value)
