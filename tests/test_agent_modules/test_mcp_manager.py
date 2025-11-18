import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agency_swarm.mcp import MCPServerOAuth, MCPServerOAuthClient
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


class _SlowCleanupServer(_DummyServer):
    def __init__(self, delay: float) -> None:
        super().__init__()
        self.delay = delay

    async def cleanup(self) -> None:
        await asyncio.sleep(self.delay)
        await super().cleanup()


class _AsyncContextServer(_DummyServer):
    def __init__(self) -> None:
        super().__init__()
        self.context_entered = 0
        self.context_exited = 0

    async def __aenter__(self) -> "_AsyncContextServer":
        self.context_entered += 1
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        self.context_exited += 1
        return False


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


@pytest.mark.asyncio
async def test_shutdown_handles_cleanup_timeout() -> None:
    manager = PersistentMCPServerManager()
    server = _SlowCleanupServer(delay=0.1)

    manager._timeouts["cleanup"] = 0.01

    await manager.ensure_connected(server)

    try:
        await manager.shutdown()
    except TimeoutError as exc:  # pragma: no cover - current behavior under test
        pytest.fail(f"shutdown should not propagate TimeoutError: {exc}")

    assert manager._drivers == {}


@pytest.mark.asyncio
async def test_proxy_supports_async_context_manager() -> None:
    manager = PersistentMCPServerManager()
    server = _AsyncContextServer()

    await manager.ensure_connected(server)
    proxy = LoopAffineAsyncProxy(server, manager)

    try:
        async with proxy as acquired:
            assert acquired is server
            assert server.context_entered == 1
            assert server.context_exited == 0
    finally:
        await manager.shutdown()

    assert server.context_entered == 1
    assert server.context_exited == 1


def test_update_oauth_cache_dir_updates_clients(tmp_path: Path) -> None:
    manager = PersistentMCPServerManager()
    server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    client = MCPServerOAuthClient(server)
    client._oauth_provider = SimpleNamespace(storage=SimpleNamespace(base_cache_dir=Path("/default-cache")))

    manager.register(server)
    manager._drivers[client] = {"real": client}

    manager.update_oauth_cache_dir(tmp_path)

    assert server.cache_dir == tmp_path
    assert client.oauth_config.cache_dir == tmp_path
    assert client._oauth_provider.storage.base_cache_dir == tmp_path
