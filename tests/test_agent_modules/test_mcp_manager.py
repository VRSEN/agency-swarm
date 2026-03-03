from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

import agency_swarm.tools.mcp_manager as mcp_manager
from agency_swarm.tools.mcp_manager import LoopAffineAsyncProxy, PersistentMCPServerManager


class _DummyServer:
    def __init__(self, name: str = "dummy") -> None:
        self.name = name
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


class _FailingCleanupServer(_DummyServer):
    async def cleanup(self) -> None:
        raise RuntimeError("cleanup failed")


class _AsyncContextServer(_DummyServer):
    def __init__(self) -> None:
        super().__init__()
        self.context_entered = 0
        self.context_exited = 0

    async def __aenter__(self) -> _AsyncContextServer:
        self.context_entered += 1
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        self.context_exited += 1
        return False


class _SyncContextServer(_DummyServer):
    def __init__(self) -> None:
        super().__init__()
        self.context_entered = 0
        self.context_exited = 0
        self.value = 42

    def __aenter__(self) -> _SyncContextServer:
        self.context_entered += 1
        return self

    def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        self.context_exited += 1
        return False

    async def ping(self, payload: str) -> str:
        return f"pong:{payload}"


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
async def test_reconnect_replaces_driver_and_resets_session() -> None:
    manager = PersistentMCPServerManager()
    server = _DummyServer()
    await manager.ensure_connected(server)
    old_state = manager._drivers[server]

    try:
        proxy = LoopAffineAsyncProxy(server, manager)
        await manager.reconnect(proxy)

        assert server.session is not None
        assert manager._drivers[server] is not old_state
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
async def test_shutdown_logs_cleanup_exception(caplog: pytest.LogCaptureFixture) -> None:
    manager = PersistentMCPServerManager()
    server = _FailingCleanupServer()
    await manager.ensure_connected(server)

    with caplog.at_level(logging.WARNING):
        await manager.shutdown()

    assert "Error during MCP server 'dummy' shutdown" in caplog.text


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


@pytest.mark.asyncio
async def test_proxy_rejects_missing_context_methods() -> None:
    manager = PersistentMCPServerManager()
    proxy = LoopAffineAsyncProxy(_DummyServer(), manager)

    with pytest.raises(TypeError, match="does not support asynchronous context management"):
        await proxy.__aenter__()

    with pytest.raises(TypeError, match="does not support asynchronous context management"):
        await proxy.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_proxy_supports_sync_context_and_method_proxying() -> None:
    manager = PersistentMCPServerManager()
    server = _SyncContextServer()

    await manager.ensure_connected(server)
    proxy = LoopAffineAsyncProxy(server, manager)

    try:
        acquired = await proxy.__aenter__()
        assert acquired is server
        assert server.context_entered == 1

        assert await proxy.ping("ok") == "pong:ok"
        assert proxy.value == 42

        await proxy.__aexit__(None, None, None)
        assert server.context_exited == 1
    finally:
        await manager.shutdown()


def test_register_get_all_and_mark_atexit() -> None:
    manager = PersistentMCPServerManager()
    named = _DummyServer(name="persisted")
    duplicate = _DummyServer(name="persisted")
    unnamed = _DummyServer(name="")

    assert manager.register(named) is named
    assert manager.register(duplicate) is named
    assert manager.register(unnamed) is unnamed

    assert manager.get("persisted") is named
    assert manager.get("missing") is None
    assert manager.all() == [named]

    assert manager.mark_atexit_registered() is True
    assert manager.mark_atexit_registered() is False


def test_shutdown_sync_noop_when_lock_already_held() -> None:
    manager = PersistentMCPServerManager()
    assert manager._sync_shutdown_lock.acquire(blocking=False) is True
    try:
        manager.shutdown_sync()
    finally:
        manager._sync_shutdown_lock.release()


def test_shutdown_sync_logs_non_loop_runtime_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    manager = PersistentMCPServerManager()

    def fake_run(coro: Any) -> None:
        coro.close()
        raise RuntimeError("other runtime")

    monkeypatch.setattr(mcp_manager.asyncio, "run", fake_run)

    with caplog.at_level(logging.WARNING):
        manager.shutdown_sync()

    assert "Error during persistent MCP manager shutdown: other runtime" in caplog.text


def test_shutdown_sync_schedules_shutdown_when_loop_running(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = PersistentMCPServerManager()
    scheduled: list[Any] = []

    def fake_run(coro: Any) -> None:
        coro.close()
        raise RuntimeError("asyncio.run() cannot be called from a running event loop")

    class _FakeLoop:
        def create_task(self, coro: Any) -> None:
            scheduled.append(coro)
            coro.close()

    monkeypatch.setattr(mcp_manager.asyncio, "run", fake_run)
    monkeypatch.setattr(mcp_manager.asyncio, "get_running_loop", lambda: _FakeLoop())

    manager.shutdown_sync()

    assert len(scheduled) == 1


def test_shutdown_sync_logs_when_loop_lookup_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    manager = PersistentMCPServerManager()

    def fake_run(coro: Any) -> None:
        coro.close()
        raise RuntimeError("asyncio.run() cannot be called from a running event loop")

    def fake_get_running_loop() -> Any:
        raise RuntimeError("no running loop")

    monkeypatch.setattr(mcp_manager.asyncio, "run", fake_run)
    monkeypatch.setattr(mcp_manager.asyncio, "get_running_loop", fake_get_running_loop)

    with caplog.at_level(logging.WARNING):
        manager.shutdown_sync()

    assert "Error during persistent MCP manager shutdown: no running loop" in caplog.text


def test_shutdown_sync_logs_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    manager = PersistentMCPServerManager()

    def fake_run(coro: Any) -> None:
        coro.close()
        raise ValueError("boom")

    monkeypatch.setattr(mcp_manager.asyncio, "run", fake_run)

    with caplog.at_level(logging.WARNING):
        manager.shutdown_sync()

    assert "Error during persistent MCP manager shutdown: boom" in caplog.text


@pytest.mark.asyncio
async def test_attach_persistent_mcp_servers_handles_invalid_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_manager = SimpleNamespace(
        get=lambda _name: None,
        register=lambda server: server,
        ensure_connected=lambda _server: asyncio.sleep(0),
    )
    monkeypatch.setattr(mcp_manager, "default_mcp_manager", fake_manager)

    await mcp_manager.attach_persistent_mcp_servers(SimpleNamespace(agents=None))
    await mcp_manager.attach_persistent_mcp_servers(
        SimpleNamespace(agents={"agent": SimpleNamespace(mcp_servers="not-a-list")})
    )


@pytest.mark.asyncio
async def test_attach_persistent_mcp_servers_rejects_missing_name(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_manager = SimpleNamespace(
        get=lambda _name: None,
        register=lambda server: server,
        ensure_connected=lambda _server: asyncio.sleep(0),
    )
    monkeypatch.setattr(mcp_manager, "default_mcp_manager", fake_manager)

    agency = SimpleNamespace(agents={"agent": SimpleNamespace(mcp_servers=[SimpleNamespace(name="")])})

    with pytest.raises(ValueError, match="has no name provided"):
        await mcp_manager.attach_persistent_mcp_servers(agency)


@pytest.mark.asyncio
async def test_attach_persistent_mcp_servers_registers_and_connects(monkeypatch: pytest.MonkeyPatch) -> None:
    connected: list[Any] = []
    store: dict[str, Any] = {}

    class _FakeManager:
        def get(self, name: str) -> Any | None:
            return store.get(name)

        def register(self, server: Any) -> Any:
            store[server.name] = server
            return server

        async def ensure_connected(self, server: Any) -> None:
            connected.append(server)

    monkeypatch.setattr(mcp_manager, "default_mcp_manager", _FakeManager())

    server_a = _DummyServer(name="a")
    server_b = _DummyServer(name="b")
    agent = SimpleNamespace(mcp_servers=[server_a, server_b])
    agency = SimpleNamespace(agents={"agent": agent})

    await mcp_manager.attach_persistent_mcp_servers(agency)

    assert all(isinstance(server, LoopAffineAsyncProxy) for server in agent.mcp_servers)
    assert len(connected) == 2


def test_register_and_connect_agent_servers_validates_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    ensure_driver_calls: list[Any] = []

    class _FakeManager:
        def get(self, _name: str) -> None:
            return None

        def register(self, server: Any) -> Any:
            return server

        def _ensure_driver(self, server: Any) -> None:
            ensure_driver_calls.append(server)

    monkeypatch.setattr(mcp_manager, "default_mcp_manager", _FakeManager())

    mcp_manager.register_and_connect_agent_servers(SimpleNamespace(mcp_servers=None))
    assert ensure_driver_calls == []

    with pytest.raises(ValueError, match="duplicate name"):
        mcp_manager.register_and_connect_agent_servers(
            SimpleNamespace(mcp_servers=[_DummyServer(name="same"), _DummyServer(name="same")])
        )

    with pytest.raises(ValueError, match="has no name provided"):
        mcp_manager.register_and_connect_agent_servers(SimpleNamespace(mcp_servers=[SimpleNamespace(name="")]))


def test_register_and_connect_agent_servers_reuses_persistent_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = _DummyServer(name="existing")
    registered: list[Any] = []
    ensured: list[Any] = []

    class _FakeManager:
        def get(self, name: str) -> Any | None:
            if name == "existing":
                return existing
            return None

        def register(self, server: Any) -> Any:
            registered.append(server)
            return server

        def _ensure_driver(self, server: Any) -> None:
            ensured.append(server)

    monkeypatch.setattr(mcp_manager, "default_mcp_manager", _FakeManager())

    agent = SimpleNamespace(mcp_servers=[_DummyServer(name="existing"), _DummyServer(name="new")])
    mcp_manager.register_and_connect_agent_servers(agent)

    assert all(isinstance(server, LoopAffineAsyncProxy) for server in agent.mcp_servers)
    assert len(registered) == 1
    assert registered[0].name == "new"
    assert ensured == [existing, registered[0]]


def test_convert_mcp_servers_to_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    added_tools: list[str] = []
    agent = SimpleNamespace(
        mcp_servers=["server"],
        mcp_config={"convert_schemas_to_strict": True},
        add_tool=lambda tool: added_tools.append(tool),
    )

    with patch("agency_swarm.tools.tool_factory.ToolFactory.from_mcp", return_value=["a", "b"]) as mock_from_mcp:
        mcp_manager.convert_mcp_servers_to_tools(agent)

    assert mock_from_mcp.call_count == 1
    assert mock_from_mcp.call_args.kwargs == {
        "convert_schemas_to_strict": True,
        "context": None,
        "agent": agent,
    }
    assert added_tools == ["a", "b"]
    assert agent.mcp_servers == []
