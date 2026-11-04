"""OAuth tasks finish with the transport that owns their event queue."""

import asyncio
from collections.abc import AsyncGenerator

import pytest

from agency_swarm import Agency, Agent
from agency_swarm.agent.execution_stream_response import StreamingRunResponse
from agency_swarm.integrations.fastapi_utils import endpoint_handlers
from agency_swarm.integrations.fastapi_utils.oauth_helpers import _encode_oauth
from agency_swarm.integrations.fastapi_utils.oauth_support import FastAPIOAuthRuntime, OAuthStateRegistry
from agency_swarm.integrations.fastapi_utils.stream_lifecycle import _StreamLifecycle


async def test_authorization_cancels_keepalive_before_streaming(monkeypatch: pytest.MonkeyPatch) -> None:
    agency = Agency(Agent(name="OAuth lifecycle", instructions="No model calls"))
    runtime = FastAPIOAuthRuntime(OAuthStateRegistry(), "user", timeout=10)
    connected = asyncio.Event()

    async def connect(_agency: Agency) -> None:
        await runtime.handle_redirect("https://example.com/authorize?state=state-1", "server")
        await connected.wait()

    async def source() -> AsyncGenerator[dict]:
        yield {"type": "response"}

    monkeypatch.setattr(endpoint_handlers, "attach_persistent_mcp_servers", connect)
    monkeypatch.setattr(endpoint_handlers, "OAUTH_KEEPALIVE_SECONDS", 3600)
    lifecycle = _StreamLifecycle(agency, StreamingRunResponse(source()), runtime, _encode_oauth)
    iterator = lifecycle.events()
    frames = [await anext(iterator), await anext(iterator)]
    await runtime._put_event({"type": "oauth_status", "state": "state-1", "status": "authorized"})
    frames.append(await anext(iterator))
    connected.set()
    frames.extend([frame async for frame in iterator])
    await lifecycle.close()

    assert "oauth_redirect" in frames[0]
    assert '"pending"' in frames[1]
    assert '"authorized"' in frames[2]
    assert frames[3] == {"type": "response"}
    assert not lifecycle._tasks
