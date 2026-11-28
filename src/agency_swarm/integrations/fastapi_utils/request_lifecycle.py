"""Cancellation-safe waiting for request resource cleanup."""

import asyncio

import anyio


async def _wait_for_cleanup[T](task: asyncio.Task[T]) -> T:
    """Finish owned cleanup before propagating cancellation to its caller.

    Shield ASGI cancellation scopes and direct asyncio cancellation. Merely
    detaching a shielded task would let /cancel report completion while the
    request still held shared-agent overrides or live producer tasks.
    """
    cancelled = False
    with anyio.CancelScope(shield=True):
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result
