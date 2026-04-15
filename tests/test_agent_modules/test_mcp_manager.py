from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

import agency_swarm.tools.mcp_manager as mcp_manager
from agency_swarm.mcp import MCPServerOAuth, MCPServerOAuthClient
from agency_swarm.mcp.oauth import FileTokenStorage, OAuthRuntimeContext, set_oauth_runtime_context, set_oauth_user_id
from agency_swarm.mcp.oauth_user import build_oauth_user_segment
from agency_swarm.tools.mcp_manager import (
    LoopAffineAsyncProxy,
    PersistentMCPServerManager,
    _build_persistence_key,
    _sync_oauth_client_handlers,
    attach_persistent_mcp_servers,
    default_mcp_manager,
)


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


class _TaskAffinityServer(_DummyServer):
    def __init__(self) -> None:
        super().__init__()
        self.task_ids: list[int] = []

    async def get_task_id(self) -> int:
        task = asyncio.current_task()
        task_id = id(task)
        self.task_ids.append(task_id)
        return task_id


class _ContextAwareServer(_DummyServer):
    def __init__(self, cache_dir: Path) -> None:
        super().__init__()
        self.storage = FileTokenStorage(cache_dir=cache_dir, server_name="ctx-server")

    async def get_user_bucket(self) -> str:
        return self.storage._get_user_cache_dir().name


class _NoCleanupServer:
    def __init__(self, name: str = "dummy") -> None:
        self.name = name
        self.session = None
        self.connect_calls = 0

    async def connect(self) -> None:
        self.connect_calls += 1
        self.session = object()


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
async def test_shutdown_skips_servers_without_cleanup(caplog: pytest.LogCaptureFixture) -> None:
    manager = PersistentMCPServerManager()
    server = _NoCleanupServer()
    await manager.ensure_connected(server)

    with caplog.at_level(logging.WARNING):
        await manager.shutdown()

    assert "Error during MCP server 'dummy' shutdown" not in caplog.text


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


@pytest.mark.asyncio
async def test_proxy_coroutine_calls_stay_on_driver_task() -> None:
    manager = PersistentMCPServerManager()
    server = _TaskAffinityServer()

    await manager.ensure_connected(server)
    proxy = LoopAffineAsyncProxy(server, manager)

    try:
        first = await proxy.get_task_id()
        second = await proxy.get_task_id()
    finally:
        await manager.shutdown()

    assert first == second
    assert len(set(server.task_ids)) == 1


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

        def register(self, server: Any, *, key: str | None = None) -> Any:
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

        def register(self, server: Any, *, key: str | None = None) -> Any:
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

        def register(self, server: Any, *, key: str | None = None) -> Any:
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


def test_register_and_connect_agent_servers_rebuilds_oauth_client_when_same_agent_is_reused_across_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: dict[str, Any] = {}
    ensured: list[Any] = []

    class _FakeManager:
        def get(self, key: str) -> Any | None:
            return registered.get(key)

        def register(self, server: Any, *, key: str | None = None) -> Any:
            assert key is not None
            registered[key] = server
            return server

        def _ensure_driver(self, server: Any) -> None:
            ensured.append(server)

    monkeypatch.setattr(mcp_manager, "default_mcp_manager", _FakeManager())

    agent = SimpleNamespace(mcp_servers=[MCPServerOAuth(url="http://localhost:8001/mcp", name="github")])

    try:
        set_oauth_user_id("user-a")
        mcp_manager.register_and_connect_agent_servers(agent)
        key_a = _build_persistence_key(agent.mcp_servers[0], "user-a")
        client_a = registered[key_a]

        set_oauth_user_id("user-b")
        mcp_manager.register_and_connect_agent_servers(agent)
        key_b = _build_persistence_key(agent.mcp_servers[0], "user-b")
        client_b = registered[key_b]

        assert client_a is not client_b
        assert getattr(agent.mcp_servers[0], "_server", agent.mcp_servers[0]) is client_b
        assert ensured == [client_a, client_b]
    finally:
        set_oauth_user_id(None)


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


@pytest.mark.asyncio
async def test_proxy_propagates_oauth_user_context_to_driver(tmp_path: Path) -> None:
    manager = PersistentMCPServerManager()
    server = _ContextAwareServer(tmp_path)

    await manager.ensure_connected(server)
    proxy = LoopAffineAsyncProxy(server, manager)

    set_oauth_user_id("user_ctx")
    try:
        bucket = await proxy.get_user_bucket()
    finally:
        set_oauth_user_id(None)
        await manager.shutdown()

    assert bucket == build_oauth_user_segment("user_ctx", max_prefix_length=120)


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


def test_update_oauth_cache_dir_replaces_previous_managed_path(tmp_path: Path) -> None:
    manager = PersistentMCPServerManager()
    old_path = tmp_path / "old"
    new_path = tmp_path / "new"
    server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    mcp_manager.apply_managed_oauth_cache_dir(server, old_path)
    client = MCPServerOAuthClient(server)

    manager.register(client)
    manager.update_oauth_cache_dir(new_path)

    assert client.oauth_config.cache_dir == new_path


def test_update_oauth_cache_dir_preserves_explicit_server_path(tmp_path: Path) -> None:
    manager = PersistentMCPServerManager()
    explicit_path = tmp_path / "explicit"
    new_path = tmp_path / "new"
    server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github", cache_dir=explicit_path)
    client = MCPServerOAuthClient(server)

    manager.register(client)
    manager.update_oauth_cache_dir(new_path)

    assert client.oauth_config.cache_dir == explicit_path


def test_resolve_method_timeout_keeps_short_list_tools_for_non_oauth_servers() -> None:
    manager = PersistentMCPServerManager()
    timeout = manager._resolve_method_timeout(_DummyServer(), "list_tools")
    assert timeout == 10.0


def test_resolve_method_timeout_extends_list_tools_for_oauth_servers() -> None:
    manager = PersistentMCPServerManager()
    oauth_server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    oauth_client = MCPServerOAuthClient(oauth_server)
    timeout = manager._resolve_method_timeout(oauth_client, "list_tools")
    assert timeout == 620.0


def test_resolve_method_timeout_prefers_runtime_timeout_for_oauth_servers() -> None:
    manager = PersistentMCPServerManager()
    oauth_server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    oauth_client = MCPServerOAuthClient(oauth_server)
    set_oauth_runtime_context(
        OAuthRuntimeContext(
            mode="saas_stream",
            user_id="user-1",
            timeout=123.0,
        )
    )
    try:
        timeout = manager._resolve_method_timeout(oauth_client, "list_tools")
    finally:
        set_oauth_runtime_context(None)
        set_oauth_user_id(None)
    assert timeout == 123.0


def test_sync_oauth_client_handlers_refreshes_runtime_handlers() -> None:
    oauth_config = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")

    async def first_redirect(_auth_url: str) -> None:
        return None

    async def first_callback() -> tuple[str, str | None]:
        return ("code-1", None)

    async def second_redirect(_auth_url: str) -> None:
        return None

    async def second_callback() -> tuple[str, str | None]:
        return ("code-2", None)

    persistent = MCPServerOAuthClient(
        oauth_config,
        {"redirect": first_redirect, "callback": first_callback},
    )
    persistent.session = object()
    persistent._authenticated = True
    persistent._oauth_provider = SimpleNamespace(
        context=SimpleNamespace(
            redirect_handler=first_redirect,
            callback_handler=first_callback,
        )
    )

    candidate = MCPServerOAuthClient(oauth_config)

    set_oauth_runtime_context(
        OAuthRuntimeContext(
            mode="saas_stream",
            user_id="user-1",
            redirect_handler_factory=lambda _server_name: second_redirect,
            callback_handler_factory=lambda _server_name: second_callback,
        )
    )
    try:
        _sync_oauth_client_handlers(persistent, candidate)

        assert persistent._redirect_handler is second_redirect
        assert persistent._callback_handler is second_callback
        assert persistent._oauth_provider is not None
        assert persistent._oauth_provider.context.redirect_handler is second_redirect
        assert persistent._oauth_provider.context.callback_handler is second_callback
        assert persistent.session is not None
        assert persistent._authenticated is True
    finally:
        set_oauth_runtime_context(None)
        set_oauth_user_id(None)


def test_sync_oauth_client_handlers_allows_static_server_handlers() -> None:
    async def first_redirect(_auth_url: str) -> None:
        return None

    async def first_callback() -> tuple[str, str | None]:
        return ("code-1", None)

    async def second_redirect(_auth_url: str) -> None:
        return None

    async def second_callback() -> tuple[str, str | None]:
        return ("code-2", None)

    persistent = MCPServerOAuthClient(
        MCPServerOAuth(
            url="http://localhost:8001/mcp",
            name="github",
            redirect_handler=first_redirect,
            callback_handler=first_callback,
        ),
        {"redirect": first_redirect, "callback": first_callback},
    )
    persistent._oauth_provider = SimpleNamespace(
        context=SimpleNamespace(
            redirect_handler=first_redirect,
            callback_handler=first_callback,
        )
    )

    candidate = MCPServerOAuthClient(
        MCPServerOAuth(
            url="http://localhost:8001/mcp",
            name="github",
            redirect_handler=second_redirect,
            callback_handler=second_callback,
        ),
        {"redirect": second_redirect, "callback": second_callback},
    )

    _sync_oauth_client_handlers(persistent, candidate)

    assert persistent._redirect_handler is second_redirect
    assert persistent._callback_handler is second_callback
    assert persistent._oauth_provider.context.redirect_handler is second_redirect
    assert persistent._oauth_provider.context.callback_handler is second_callback


@pytest.mark.asyncio
async def test_attach_persistent_does_not_cache_request_scoped_oauth_handlers() -> None:
    """Request-scoped OAuth handlers should come from contextvars, not cached clients."""
    await default_mcp_manager.shutdown()

    try:
        set_oauth_runtime_context(
            OAuthRuntimeContext(
                mode="saas_stream",
                user_id="user-1",
                timeout=123.0,
            )
        )
        first_agent = SimpleNamespace(
            mcp_servers=[MCPServerOAuth(url="http://localhost:8001/mcp", name="github")],
            mcp_oauth_handler_factory=lambda server_name: {
                "redirect": lambda auth_url: ("req1", auth_url, server_name),
                "callback": lambda: ("code1", server_name),
            },
        )
        first_agency = SimpleNamespace(agents={"a": first_agent})
        await attach_persistent_mcp_servers(first_agency)

        key = _build_persistence_key(first_agent.mcp_servers[0], "user-1")
        first_client = default_mcp_manager.get(key)
        assert first_client is not None
        first_redirect = getattr(first_client, "_redirect_handler", None)
        first_callback = getattr(first_client, "_callback_handler", None)

        second_agent = SimpleNamespace(
            mcp_servers=[MCPServerOAuth(url="http://localhost:8001/mcp", name="github")],
            mcp_oauth_handler_factory=lambda server_name: {
                "redirect": lambda auth_url: ("req2", auth_url, server_name),
                "callback": lambda: ("code2", server_name),
            },
        )
        second_agency = SimpleNamespace(agents={"a": second_agent})
        await attach_persistent_mcp_servers(second_agency)

        reused_client = default_mcp_manager.get(key)
        assert reused_client is not None
        reused_redirect = getattr(reused_client, "_redirect_handler", None)
        reused_callback = getattr(reused_client, "_callback_handler", None)

        assert reused_client is first_client
        assert first_redirect is None
        assert first_callback is None
        assert reused_redirect is None
        assert reused_callback is None
    finally:
        set_oauth_runtime_context(None)
        await default_mcp_manager.shutdown()


@pytest.mark.asyncio
async def test_attach_persistent_isolates_oauth_clients_by_user_id() -> None:
    """OAuth persistent clients should be keyed by (server_name, user_id)."""
    await default_mcp_manager.shutdown()

    try:
        user_a_agent = SimpleNamespace(
            mcp_servers=[MCPServerOAuth(url="http://localhost:8001/mcp", name="github")],
        )
        user_a_agency = SimpleNamespace(agents={"a": user_a_agent})
        set_oauth_user_id("user-a")
        await attach_persistent_mcp_servers(user_a_agency)

        user_b_agent = SimpleNamespace(
            mcp_servers=[MCPServerOAuth(url="http://localhost:8001/mcp", name="github")],
        )
        user_b_agency = SimpleNamespace(agents={"b": user_b_agent})
        set_oauth_user_id("user-b")
        await attach_persistent_mcp_servers(user_b_agency)

        key_a = _build_persistence_key(user_a_agent.mcp_servers[0], "user-a")
        key_b = _build_persistence_key(user_b_agent.mcp_servers[0], "user-b")
        client_a = default_mcp_manager.get(key_a)
        client_b = default_mcp_manager.get(key_b)

        assert client_a is not None
        assert client_b is not None
        assert client_a is not client_b
    finally:
        set_oauth_user_id(None)
        await default_mcp_manager.shutdown()


@pytest.mark.asyncio
async def test_attach_persistent_rebuilds_oauth_client_when_same_agent_is_reused_across_users() -> None:
    """Reusing one agent instance across users must not alias the first user's OAuth client."""
    await default_mcp_manager.shutdown()

    try:
        agent = SimpleNamespace(
            mcp_servers=[MCPServerOAuth(url="http://localhost:8001/mcp", name="github")],
        )
        agency = SimpleNamespace(agents={"a": agent})

        set_oauth_user_id("user-a")
        await attach_persistent_mcp_servers(agency)
        key_a = _build_persistence_key(agent.mcp_servers[0], "user-a")
        client_a = default_mcp_manager.get(key_a)

        set_oauth_user_id("user-b")
        await attach_persistent_mcp_servers(agency)
        key_b = _build_persistence_key(agent.mcp_servers[0], "user-b")
        client_b = default_mcp_manager.get(key_b)

        assert client_a is not None
        assert client_b is not None
        assert client_a is not client_b
        assert getattr(agent.mcp_servers[0], "_server", agent.mcp_servers[0]) is client_b
    finally:
        set_oauth_user_id(None)
        await default_mcp_manager.shutdown()


def test_build_persistence_key_keeps_distinct_user_ids_separate() -> None:
    oauth_server = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    oauth_client = MCPServerOAuthClient(oauth_server)

    key_plus = _build_persistence_key(oauth_client, "alice+bob")
    key_underscore = _build_persistence_key(oauth_client, "alice_bob")

    assert key_plus != key_underscore
    assert key_plus.startswith("github::oauth::")
    assert key_underscore.startswith("github::oauth::")


def test_build_persistence_key_separates_oauth_cache_dirs(tmp_path: Path) -> None:
    server_a = MCPServerOAuth(url="http://localhost:8001/mcp", name="github", cache_dir=tmp_path / "a")
    server_b = MCPServerOAuth(url="http://localhost:8001/mcp", name="github", cache_dir=tmp_path / "b")

    key_a = _build_persistence_key(MCPServerOAuthClient(server_a), "user-a")
    key_b = _build_persistence_key(MCPServerOAuthClient(server_b), "user-a")

    assert key_a != key_b
    assert key_a.startswith("github::oauth::")
    assert key_b.startswith("github::oauth::")


def test_build_persistence_key_separates_oauth_server_urls() -> None:
    server_a = MCPServerOAuth(url="http://localhost:8001/mcp", name="github")
    server_b = MCPServerOAuth(url="http://localhost:8002/mcp", name="github")

    key_a = _build_persistence_key(MCPServerOAuthClient(server_a), "user-a")
    key_b = _build_persistence_key(MCPServerOAuthClient(server_b), "user-a")

    assert key_a != key_b
    assert key_a.startswith("github::oauth::")
    assert key_b.startswith("github::oauth::")


def test_build_persistence_key_separates_custom_storage(tmp_path: Path) -> None:
    storage_a = FileTokenStorage(cache_dir=tmp_path / "a", server_name="github")
    storage_b = FileTokenStorage(cache_dir=tmp_path / "b", server_name="github")
    server_a = MCPServerOAuth(url="http://localhost:8001/mcp", name="github", storage=storage_a)
    server_b = MCPServerOAuth(url="http://localhost:8001/mcp", name="github", storage=storage_b)

    key_a = _build_persistence_key(MCPServerOAuthClient(server_a), "user-a")
    key_b = _build_persistence_key(MCPServerOAuthClient(server_b), "user-a")

    assert key_a != key_b
