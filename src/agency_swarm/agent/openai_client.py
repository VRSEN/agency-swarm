"""Event-loop-scoped lifecycle for the shared OpenAI HTTP client.

The Agents SDK pools keep-alive connections in one process-wide
``httpx2.AsyncClient`` (``agents.models.openai_provider.shared_http_client``).
Under httpx2/httpcore2 a pooled connection is bound to the event loop that
created it, so a second loop — another ``asyncio.run`` call, a pytest-asyncio
test, or a FastAPI worker after a sync call — crashes with
``RuntimeError: Event loop is closed`` or
``asyncio.locks.Event ... bound to a different event loop``.

Scoping the shared client to the running loop preserves the SDK's pooling
intent without sharing transports across loops: each live loop owns one
pooled client and entries for closed loops are dropped so transports can be
garbage-collected.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import httpx2
from agents.models import openai_provider as _agents_openai_provider
from openai import AsyncOpenAI, DefaultAsyncHttpx2Client

_http_clients_by_loop: dict[asyncio.AbstractEventLoop, httpx2.AsyncClient] = {}
_openai_clients_by_loop: dict[asyncio.AbstractEventLoop, AsyncOpenAI] = {}
_registry_lock = threading.RLock()
_patch_installed = False


def _drop_closed_loop_clients() -> None:
    """Release registry entries whose loop is closed so transports can be GC'd."""
    for loop in [loop for loop in _http_clients_by_loop if loop.is_closed()]:
        _http_clients_by_loop.pop(loop, None)
        _openai_clients_by_loop.pop(loop, None)


def shared_http_client() -> httpx2.AsyncClient:
    """Return the shared ``httpx2.AsyncClient`` owned by the running event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop to bind to; a fresh client binds to the loop that issues its
        # first request, matching stock SDK behavior.
        return DefaultAsyncHttpx2Client()
    with _registry_lock:
        client = _http_clients_by_loop.get(loop)
        if client is None or client.is_closed:
            _drop_closed_loop_clients()
            client = DefaultAsyncHttpx2Client()
            _http_clients_by_loop[loop] = client
        return client


def loop_scoped_openai_client() -> AsyncOpenAI:
    """Return an ``AsyncOpenAI`` whose connection pool is bound to the running loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop to bind to; a loop-scoped client resolves the caller's pool
        # per request, so the instance stays usable across later loops.
        return AsyncOpenAI(http_client=loop_scoped_http_client())
    with _registry_lock:
        client = _openai_clients_by_loop.get(loop)
        if client is None or client.is_closed():
            client = AsyncOpenAI(http_client=shared_http_client())
            _openai_clients_by_loop[loop] = client
        return client


def install_loop_scoped_http_client() -> None:
    """Scope the Agents SDK shared HTTP client to the running event loop.

    The SDK only calls ``shared_http_client()`` when a provider has no explicit
    ``openai_client``, so caller-supplied clients keep their own lifecycle.

    Remaining SDK-level gaps are intentionally left alone: ``Model._get_client``
    builds a bare ``AsyncOpenAI()`` when a model is constructed with
    ``openai_client=None``, and ``set_default_openai_client`` accepts a fixed
    client. Both keep their own (loop-bound) lifecycle; Agency Swarm model
    builders always pass a ``loop_scoped_http_client()`` instead.
    """
    global _patch_installed
    with _registry_lock:
        if _patch_installed:
            return
        # Both SDK providers share the same process-wide client pattern.
        _agents_openai_provider.shared_http_client = shared_http_client
        try:
            # Local import: ``agents.voice`` transitively requires numpy and
            # websockets, which only ship with the ``voice`` extra. Skip the
            # patch when they are absent so base installs can import and
            # construct agents without them.
            from agents.voice.models import openai_model_provider as agents_voice_provider
        except ImportError:
            pass
        else:
            agents_voice_provider.shared_http_client = shared_http_client
        _patch_installed = True


class _LoopScopedHttpClient(httpx2.AsyncClient):
    """HTTP client that routes each request through the running loop's pool.

    ``AsyncOpenAI`` instances stored on long-lived objects — a model built at
    agent construction time — outlive the event loop that issues their first
    request. A fixed ``AsyncClient`` pools connections bound to that first loop
    and crashes on the next ``asyncio.run``. This client holds no pool of its
    own: every ``send`` resolves ``shared_http_client()`` for the loop running
    it, so requests always run on the caller's loop.
    """

    async def send(
        self,
        request: httpx2.Request,
        *,
        stream: bool = False,
        **kwargs: Any,
    ) -> httpx2.Response:
        if self.is_closed:
            raise RuntimeError("Cannot send a request, as the client has been closed.")
        return await shared_http_client().send(request, stream=stream, **kwargs)


def loop_scoped_http_client() -> httpx2.AsyncClient:
    """Return an ``httpx2.AsyncClient`` whose requests run on the caller's loop.

    Safe to store on ``AsyncOpenAI`` instances kept across event loops, such as
    a model object cached on an ``Agent``. Each call returns a new client so the
    owning ``AsyncOpenAI`` keeps its own close semantics; the pooled transports
    live in the per-loop shared registry, not on this client.
    """
    return _LoopScopedHttpClient()
