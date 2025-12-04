from __future__ import annotations

import pytest

from agency_swarm import Agency, Agent


@pytest.fixture
def agency_factory():
    """Factory function to create a test agency."""

    def create_agency(load_threads_callback=None, save_threads_callback=None):
        agent = Agent(name="TestAgent", instructions="Base instructions")
        return Agency(
            agent,
            load_threads_callback=load_threads_callback,
            save_threads_callback=save_threads_callback,
        )

    return create_agency
