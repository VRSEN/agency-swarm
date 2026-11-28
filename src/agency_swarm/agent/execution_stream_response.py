import asyncio
import logging
from collections.abc import AsyncGenerator, Callable
from typing import Any, cast

from agents import RunResultStreaming
from agents.stream_events import StreamEvent

logger = logging.getLogger(__name__)


def _create_future() -> asyncio.Future[Any]:
    loop = asyncio.get_running_loop()
    return loop.create_future()


class StreamingRunResponse(AsyncGenerator[StreamEvent | dict[str, Any]]):
    """Wrap an async generator while preserving the eventual ``RunResultStreaming``.

    The wrapper mirrors the generator interface (`__aiter__`, `asend`, etc.) so
    callers can stream events immediately, but it also tracks the final result
    (or exception) using an internal future. Guardrail retries and nested
    streams adopt each other's futures via :meth:`_adopt_stream`, ensuring a
    single completion signal. Consumers can inspect :attr:`final_result`,
    :attr:`final_output`, or await :meth:`wait_final_result` even after the
    streaming generator has been closed.
    """

    def __init__(
        self,
        generator: AsyncGenerator[StreamEvent | dict[str, Any]],
        *,
        final_future: asyncio.Future[RunResultStreaming | None] | None = None,
        on_resolve: Callable[[RunResultStreaming | None], None] | None = None,
        cancel_event: asyncio.Event | None = None,
        cancel_state: dict[str, Any] | None = None,
    ) -> None:
        self._generator = generator
        self._final_future: asyncio.Future[RunResultStreaming | None] | None = final_future
        self._inner: StreamingRunResponse | None = None
        self._on_resolve = on_resolve
        self._pending_result: RunResultStreaming | None = None
        self._pending_result_set = False
        self._pending_exception: BaseException | None = None
        self._cancel_event = cancel_event
        self._cancel_state = cancel_state  # Shared state for cancel mode
        self._cancel_mode: str | None = None

    def __aiter__(self) -> AsyncGenerator[StreamEvent | dict[str, Any]]:
        self._maybe_bind_loop()
        return self._generator

    async def __anext__(self) -> StreamEvent | dict[str, Any]:
        self._maybe_bind_loop()
        return await self._generator.__anext__()

    async def asend(self, value: Any) -> Any:
        self._maybe_bind_loop()
        return await self._generator.asend(value)

    async def athrow(self, typ: Any, val: Any = None, tb: Any = None) -> Any:
        self._maybe_bind_loop()
        return await self._generator.athrow(typ, val, tb)

    async def aclose(self) -> None:
        self._maybe_bind_loop()
        try:
            await self._close_generators()
        except asyncio.CancelledError:
            self._resolve_final_result(None)
            raise
        except BaseException as exc:
            self._resolve_exception(exc)
            raise
        else:
            if self._inner is None and (self._final_future is None or not self._final_future.done()):
                self._resolve_final_result(None)

    async def _close_generators(self) -> None:
        primary_error: BaseException | None = None
        try:
            await self._generator.aclose()
        except BaseException as exc:
            primary_error = exc
        if self._inner is not None:
            try:
                await self._inner.aclose()
            except BaseException as exc:
                if primary_error is None:
                    primary_error = exc
        if primary_error is not None:
            raise primary_error

    def cancel(self, mode: str = "immediate") -> None:
        """Signal cancellation to the underlying stream.

        After calling cancel(), continue consuming the stream to allow
        the cancellation to complete properly. The stream will stop
        producing events once the cancellation is processed.

        Args:
            mode: Cancel mode - "immediate" stops right away,
                  "after_turn" waits for the current turn to complete.
        """
        if mode not in {"immediate", "after_turn"}:
            raise ValueError(f"Unknown cancellation mode: {mode}")
        if self._inner is not None:
            self._inner.cancel(mode=mode)
            mode = self._inner._cancel_mode or mode
        if self._cancel_mode == "immediate" or self._cancel_mode == mode:
            return
        escalating = self._cancel_mode == "after_turn" and mode == "immediate"
        self._cancel_mode = mode
        if self._cancel_state is not None:
            self._cancel_state["mode"] = mode
            self._cancel_state["user_requested"] = True
        if self._inner is None and escalating and self._cancel_state is not None:
            # A worker draining after_turn has already consumed its cancel
            # waiter. Ask the SDK to interrupt that current turn directly.
            result = cast(RunResultStreaming | None, self._cancel_state.get("run_result"))
            if result is not None:
                result.cancel(mode="immediate")
        if self._cancel_event is not None:
            self._cancel_event.set()

    def _adopt_stream(self, other: "StreamingRunResponse") -> None:
        existing_future = self._final_future
        self._inner = other

        # Propagate cancel event/state bidirectionally so nested wrappers share the same state.
        if self._cancel_event is not None and other._cancel_event is None:
            other._cancel_event = self._cancel_event
        elif other._cancel_event is not None and self._cancel_event is None:
            self._cancel_event = other._cancel_event
        if self._cancel_state is not None and other._cancel_state is None:
            other._cancel_state = self._cancel_state
        elif other._cancel_state is not None and self._cancel_state is None:
            self._cancel_state = other._cancel_state

        self._bridge_final_future(other, existing_future)

        self._final_future = other._final_future or existing_future
        self._pending_result = other._pending_result
        self._pending_result_set = getattr(other, "_pending_result_set", False)
        self._pending_exception = other._pending_exception
        if self._cancel_mode is not None:
            other.cancel(mode=self._cancel_mode)

    def _bridge_final_future(
        self,
        other: "StreamingRunResponse",
        existing_future: asyncio.Future[RunResultStreaming | None] | None,
    ) -> None:
        if existing_future is not None:
            existing_loop = existing_future.get_loop()

            if other._final_future is None:
                other._final_future = existing_future
            elif other._final_future is not existing_future:

                def _sync_future(source: asyncio.Future[Any]) -> None:
                    if existing_future.done():
                        return
                    if source.cancelled():
                        existing_loop.call_soon_threadsafe(existing_future.cancel)
                        return
                    try:
                        result = source.result()
                    except BaseException as error:  # pragma: no cover - defensive
                        existing_loop.call_soon_threadsafe(existing_future.set_exception, error)
                        return
                    existing_loop.call_soon_threadsafe(existing_future.set_result, result)

                other._final_future.add_done_callback(_sync_future)
                if other._final_future.done():
                    _sync_future(other._final_future)

    def _has_inner_stream(self) -> bool:
        return self._inner is not None

    def _maybe_bind_loop(self) -> None:
        if self._inner is not None:
            self._inner._maybe_bind_loop()
            return
        if self._final_future is None:
            try:
                self._final_future = _create_future()
            except RuntimeError:
                return
        self._flush_pending()

    def _flush_pending(self) -> None:
        if self._final_future is None:
            return
        if self._pending_exception is not None and not self._final_future.done():
            self._final_future.set_exception(self._pending_exception)
            try:
                self._final_future.exception()
            except Exception:  # pragma: no cover - defensive
                pass
            self._pending_exception = None
            self._pending_result = None
            self._pending_result_set = False
        elif self._pending_result_set and not self._final_future.done():
            self._final_future.set_result(self._pending_result)
            self._pending_result = None
            self._pending_result_set = False

    def _resolve_final_result(self, result: RunResultStreaming | None) -> None:
        if self._inner is not None:
            self._inner._resolve_final_result(result)
            return
        if self._on_resolve is not None:
            try:
                self._on_resolve(result)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("StreamingRunResponse on_resolve callback failed")
        if self._final_future is None:
            try:
                self._final_future = _create_future()
            except RuntimeError:
                self._pending_result = result
                self._pending_result_set = True
                self._pending_exception = None
                return
        if not self._final_future.done():
            self._final_future.set_result(result)
        self._pending_result_set = False

    def _resolve_exception(self, exc: BaseException) -> None:
        if self._inner is not None:
            self._inner._resolve_exception(exc)
            return
        if self._on_resolve is not None:
            try:
                self._on_resolve(None)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("StreamingRunResponse on_resolve callback failed after exception")
        if self._final_future is None:
            try:
                self._final_future = _create_future()
            except RuntimeError:
                self._pending_result = None
                self._pending_result_set = False
                self._pending_exception = exc
                return
        if not self._final_future.done():
            self._final_future.set_exception(exc)
        try:
            if self._final_future.done():
                self._final_future.exception()
        except Exception:  # pragma: no cover - defensive
            pass
        self._pending_result_set = False

    @property
    def final_result(self) -> RunResultStreaming | None:
        if self._inner is not None:
            return self._inner.final_result
        if self._final_future is None:
            return self._pending_result
        if not self._final_future.done() or self._final_future.cancelled():
            return None
        try:
            return self._final_future.result()
        except Exception:
            return None

    @property
    def final_output(self) -> Any:
        result = self.final_result
        return getattr(result, "final_output", None) if result is not None else None

    async def wait_final_result(self) -> RunResultStreaming | None:
        if self._inner is not None:
            return await self._inner.wait_final_result()
        self._maybe_bind_loop()
        if self._final_future is None:
            self._final_future = _create_future()
            self._flush_pending()
        return await asyncio.shield(self._final_future)
