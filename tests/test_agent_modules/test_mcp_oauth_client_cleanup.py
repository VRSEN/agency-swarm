"""Regression tests for task-affine OAuth MCP connection cleanup."""

import asyncio
from pathlib import Path
from types import TracebackType
from unittest.mock import AsyncMock

import pytest

from agency_swarm.mcp import oauth_client as oauth_client_module
from agency_swarm.mcp.oauth import MCPServerOAuth

TEST_SERVER_URL = "http://localhost:8001/mcp"


class _ConnectFailure(RuntimeError):
    pass


class _TaskAffineContext:
    """Model AnyIO contexts that must exit from the task that entered them."""

    def __init__(self, value: object) -> None:
        self.value = value
        self.owner_task: asyncio.Task[object] | None = None
        self.exit_task: asyncio.Task[object] | None = None
        self.closed = False

    async def __aenter__(self) -> object:
        self.owner_task = asyncio.current_task()
        return self.value

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.exit_task = asyncio.current_task()
        if self.exit_task is not self.owner_task:
            raise RuntimeError("Attempted to exit cancel scope in a different task")
        self.closed = True


class _FailingSession:
    async def initialize(self) -> None:
        raise _ConnectFailure("session initialization failed")


class _BlockingSession:
    def __init__(self) -> None:
        self.initializing = asyncio.Event()

    async def initialize(self) -> None:
        self.initializing.set()
        await asyncio.Future()


def _make_client(tmp_path: Path) -> oauth_client_module.MCPServerOAuthClient:
    config = MCPServerOAuth(
        url=TEST_SERVER_URL,
        name="task-affine-cleanup",
        client_id="test-id",
        client_secret="test-secret",
        cache_dir=tmp_path,
    )
    return oauth_client_module.MCPServerOAuthClient(config)


def _install_contexts(
    monkeypatch: pytest.MonkeyPatch,
    transport_context: _TaskAffineContext,
    session_context: _TaskAffineContext,
) -> None:
    monkeypatch.setattr(
        oauth_client_module,
        "create_oauth_provider",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(
        oauth_client_module,
        "_build_streamable_transport",
        lambda url, provider: (transport_context, None),
    )
    monkeypatch.setattr(
        oauth_client_module,
        "ClientSession",
        lambda read, write: session_context,
    )


async def test_connect_failure_cleans_up_contexts_in_owner_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    transport_context = _TaskAffineContext((object(), object(), lambda: None))
    session_context = _TaskAffineContext(_FailingSession())
    _install_contexts(monkeypatch, transport_context, session_context)
    client = _make_client(tmp_path)

    with pytest.raises(_ConnectFailure, match="session initialization failed"):
        await client.connect()

    assert session_context.exit_task is session_context.owner_task
    assert transport_context.exit_task is transport_context.owner_task
    assert session_context.closed
    assert transport_context.closed


async def test_connect_cancellation_cleans_up_contexts_in_owner_task(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    blocking_session = _BlockingSession()
    transport_context = _TaskAffineContext((object(), object(), lambda: None))
    session_context = _TaskAffineContext(blocking_session)
    _install_contexts(monkeypatch, transport_context, session_context)
    client = _make_client(tmp_path)

    connect_task = asyncio.create_task(client.connect())
    await blocking_session.initializing.wait()
    connect_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await connect_task

    assert connect_task.cancelled()
    assert session_context.owner_task is connect_task
    assert session_context.exit_task is session_context.owner_task
    assert transport_context.exit_task is transport_context.owner_task
    assert session_context.closed
    assert transport_context.closed
