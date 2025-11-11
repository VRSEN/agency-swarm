"""Async Jupyter kernel helpers for the IPythonInterpreter tool."""

import asyncio
import weakref
from dataclasses import dataclass
from typing import Any

from jupyter_client import AsyncKernelManager


@dataclass(slots=True)
class ExecResult:
    """Outcome from executing code in a kernel session."""

    ok: bool
    stdout: str = ""
    result_repr: str | None = None
    ename: str | None = None
    evalue: str | None = None
    traceback: str | None = None


class AsyncKernelSession:
    """Manage a single Jupyter kernel process for one logical client."""

    def __init__(self, kernel_name: str = "python3") -> None:
        self.kernel_name = kernel_name
        self.km: AsyncKernelManager | None = None
        self.kc: Any = None  # AsyncKernelClient type not exported by jupyter_client
        self._lock = asyncio.Lock()
        self._ready = asyncio.Event()

    async def start(self) -> None:
        """Boot the kernel process if it is not already running."""
        if self.km is not None:
            return

        km = AsyncKernelManager(kernel_name=self.kernel_name)
        await km.start_kernel()
        kc = km.client()
        kc.start_channels()
        await kc.wait_for_ready()

        self.km = km
        self.kc = kc
        self._ready.set()

    async def shutdown(self) -> None:
        """Terminate the kernel process and clear state."""
        if self.km is None:
            return

        try:
            if self.kc:
                self.kc.stop_channels()
        finally:
            try:
                await self.km.shutdown_kernel(now=True)
            finally:
                self.km = None
                self.kc = None
                self._ready.clear()

    async def _restart(self, timeout: float = 30.0) -> None:
        """Restart the kernel after a crash or timeout."""
        if self.km is None:
            return

        try:
            async with asyncio.timeout(timeout):
                await self.km.restart_kernel(now=True)
                if self.kc:
                    self.kc.stop_channels()
                self.kc = self.km.client()
                self.kc.start_channels()
                await self.kc.wait_for_ready()
        except TimeoutError:
            # Kernel is truly dead, force shutdown and recreate
            await self.shutdown()
            await self.start()

    async def execute(self, code: str, timeout: float = 10.0) -> ExecResult:
        """Execute code inside the kernel, collecting stdout, result, and errors."""
        await self._ready.wait()

        async with self._lock:
            kc = self.kc
            if kc is None:
                return ExecResult(False, ename="KernelError", evalue="Kernel client is not ready")

            msg_id = kc.execute(
                code,
                store_history=False,
                allow_stdin=False,
                stop_on_error=True,
            )

            stdout_chunks: list[str] = []
            result_repr: str | None = None
            ename: str | None = None
            evalue: str | None = None
            tb_joined: str | None = None
            got_idle = False
            got_reply = False

            async def drain_iopub() -> None:
                nonlocal stdout_chunks, result_repr, ename, evalue, tb_joined, got_idle
                while True:
                    msg = await kc.get_iopub_msg(timeout=timeout)

                    if msg.get("parent_header", {}).get("msg_id") != msg_id:
                        continue

                    msg_type = msg["msg_type"]
                    content = msg["content"]

                    if msg_type == "status" and content.get("execution_state") == "idle":
                        got_idle = True
                        return
                    if msg_type == "stream":
                        if content.get("name") in ("stdout", "stderr"):
                            stdout_chunks.append(content.get("text", ""))
                    elif msg_type in {"execute_result", "display_data"}:
                        data = content.get("data", {})
                        if "text/plain" in data:
                            result_repr = data["text/plain"]
                    elif msg_type == "error":
                        ename = content.get("ename")
                        evalue = content.get("evalue")
                        traceback_list = content.get("traceback") or []
                        tb_joined = "\n".join(traceback_list)

            async def wait_shell_reply() -> None:
                nonlocal got_reply
                max_attempts = 100  # Prevent infinite drain of unrelated messages
                for _ in range(max_attempts):
                    reply = await kc.get_shell_msg(timeout=timeout)
                    if reply.get("parent_header", {}).get("msg_id") == msg_id:
                        got_reply = True
                        return
                raise RuntimeError(f"Failed to receive shell reply after {max_attempts} attempts")

            try:
                await asyncio.gather(drain_iopub(), wait_shell_reply())
            except TimeoutError:
                await self._restart()
                return ExecResult(
                    ok=False,
                    ename="TimeoutError",
                    evalue=f"Code execution exceeded {timeout} seconds",
                )
            except Exception as exc:  # pragma: no cover - defensive
                await self._restart()
                return ExecResult(False, ename=exc.__class__.__name__, evalue=str(exc))

            ok = got_idle and got_reply and ename is None
            return ExecResult(
                ok=ok,
                stdout="".join(stdout_chunks),
                result_repr=result_repr,
                ename=ename,
                evalue=evalue,
                traceback=tb_joined,
            )


class AsyncKernelPool:
    """Maintain one kernel session per client identifier."""

    def __init__(self, kernel_name: str = "python3") -> None:
        self.kernel_name = kernel_name
        self._sessions: dict[str, AsyncKernelSession] = {}
        self._pool_lock = asyncio.Lock()

        # Register automatic cleanup when pool is garbage collected
        weakref.finalize(self, self._cleanup_sessions_sync, self._sessions)

    async def get_or_create(self, client_id: str) -> AsyncKernelSession:
        if client_id not in self._sessions:
            async with self._pool_lock:
                # Double-check after acquiring lock to prevent race condition
                if client_id not in self._sessions:
                    session = AsyncKernelSession(self.kernel_name)
                    await session.start()
                    self._sessions[client_id] = session
        return self._sessions[client_id]

    async def execute(self, client_id: str, code: str, timeout: float = 10.0) -> ExecResult:
        session = await self.get_or_create(client_id)
        return await session.execute(code, timeout=timeout)

    async def shutdown(self, client_id: str) -> None:
        session = self._sessions.pop(client_id, None)
        if session is not None:
            await session.shutdown()

    async def shutdown_all(self) -> None:
        for client_id in list(self._sessions.keys()):
            await self.shutdown(client_id)

    @staticmethod
    def _cleanup_sessions_sync(sessions: dict[str, AsyncKernelSession]) -> None:
        """Synchronous cleanup wrapper called by weakref.finalize on GC."""
        if not sessions:
            return

        try:
            # Try to get existing event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                should_close_loop = True
            else:
                should_close_loop = False

            # Shutdown all sessions
            async def _shutdown_all():
                for session in list(sessions.values()):
                    try:
                        await session.shutdown()
                    except Exception:
                        pass  # Silent failure during cleanup
                sessions.clear()

            if should_close_loop:
                loop.run_until_complete(_shutdown_all())
                loop.close()
            else:
                # Schedule on existing loop
                asyncio.create_task(_shutdown_all())
        except Exception:
            pass  # Silent failure in cleanup
