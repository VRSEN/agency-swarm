import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from agency_swarm.mcp import MCPServerOAuth, MCPServerOAuthClient
from agency_swarm.tools.mcp_manager import (
    LoopAffineAsyncProxy,
    PersistentMCPServerManager,
    attach_persistent_mcp_servers,
    default_mcp_manager,
)


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


@pytest.mark.asyncio
async def test_attach_persistent_updates_oauth_handlers_per_request() -> None:
    """Persistent OAuth client should adopt per-request handlers before reuse."""
    await default_mcp_manager.shutdown()

    try:
        first_agent = SimpleNamespace(
            mcp_servers=[MCPServerOAuth(url="http://localhost:8001/mcp", name="github")],
            mcp_oauth_handler_factory=lambda server_name: {
                "redirect": lambda auth_url: ("req1", auth_url, server_name),
                "callback": lambda: ("code1", server_name),
            },
        )
        first_agency = SimpleNamespace(agents={"a": first_agent})
        await attach_persistent_mcp_servers(first_agency)

        first_client = default_mcp_manager.get("github")
        first_redirect = getattr(first_client, "_redirect_handler", None)

        second_agent = SimpleNamespace(
            mcp_servers=[MCPServerOAuth(url="http://localhost:8001/mcp", name="github")],
            mcp_oauth_handler_factory=lambda server_name: {
                "redirect": lambda auth_url: ("req2", auth_url, server_name),
                "callback": lambda: ("code2", server_name),
            },
        )
        second_agency = SimpleNamespace(agents={"a": second_agent})
        await attach_persistent_mcp_servers(second_agency)

        reused_client = default_mcp_manager.get("github")
        reused_redirect = getattr(reused_client, "_redirect_handler", None)

        assert reused_client is first_client
        assert reused_redirect is not None
        assert reused_redirect is not first_redirect
        assert reused_redirect("auth-url") == ("req2", "auth-url", "github")
    finally:
        await default_mcp_manager.shutdown()
