import asyncio

import pytest

from agency_swarm.util.helpers import run_async_sync


async def add(a, b):
    await asyncio.sleep(0)
    return a + b


def test_run_async_sync_basic():
    assert run_async_sync(add, 1, 2) == 3


@pytest.mark.asyncio
async def test_run_async_sync_in_running_loop():
    with pytest.raises(RuntimeError):
        run_async_sync(add, 1, 2)
