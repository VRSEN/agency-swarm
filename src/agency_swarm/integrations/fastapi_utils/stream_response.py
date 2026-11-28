"""ASGI response ownership for leased streaming requests."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable

from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.types import Receive, Scope, Send

from agency_swarm.integrations.fastapi_utils.request_lifecycle import _wait_for_cleanup


class _OwnedStreamingResponse(StreamingResponse):
    """Close the body and request even when ASGI send fails before iteration."""

    def __init__(
        self,
        body: AsyncGenerator[str],
        cleanup: Callable[[], Awaitable[None]],
        *,
        media_type: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(body, media_type=media_type, headers=headers, background=BackgroundTask(cleanup))
        self._owned_body = body
        self._cleanup = cleanup

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                await _wait_for_cleanup(asyncio.create_task(self._owned_body.aclose()))
            finally:
                await self._cleanup()
