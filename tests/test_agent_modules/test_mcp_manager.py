import pytest

from agency_swarm.tools.mcp_manager import LoopAffineAsyncProxy, PersistentMCPServerManager


class _DummyServer:
    def __init__(self) -> None:
        self.name = "dummy"
        self.session = None
        self.connect_calls = 0

    async def connect(self) -> None:
        self.connect_calls += 1
        self.session = object()

    async def cleanup(self) -> None:
        self.session = None


@pytest.mark.asyncio
async def test_ensure_connected_reuses_driver_for_proxy() -> None:
    manager = PersistentMCPServerManager()
    server = _DummyServer()

    await manager.ensure_connected(server)
    proxy = LoopAffineAsyncProxy(server, manager)

    await manager.ensure_connected(proxy)

    try:
        assert len(manager._drivers) == 1
    finally:
        await manager.shutdown()
