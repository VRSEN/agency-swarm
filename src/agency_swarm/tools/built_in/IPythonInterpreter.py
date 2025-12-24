# ipython_interpreter.py
"""IPython interpreter tool with isolated kernel execution per agent."""

from __future__ import annotations

import asyncio
import os
import weakref
from dataclasses import dataclass
from typing import Any

from pydantic import Field

from agency_swarm.tools.base_tool import BaseTool

# Import jupyter dependencies (will fail with clear error if not installed)
try:
    from jupyter_client import AsyncKernelManager  # type: ignore[import-not-found]
except ImportError as e:
    raise ImportError(
        "IPythonInterpreter requires jupyter packages. Install them with: pip install agency-swarm[jupyter]"
    ) from e


# Default timeout for code execution (seconds)
DEFAULT_TIMEOUT_SECONDS: float = float(os.getenv("PERSISTENT_SHELL_TIMEOUT", "60.0"))


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

        await self._apply_nest_asyncio(kc)

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
                await self._apply_nest_asyncio(self.kc)
        except TimeoutError:
            # Kernel is truly dead, force shutdown and recreate
            await self.shutdown()
            await self.start()

    async def execute(
        self, code: str, timeout: float = DEFAULT_TIMEOUT_SECONDS, working_dir: str | None = None
    ) -> ExecResult:
        """Execute code inside the kernel, collecting stdout, result, and errors."""
        await self._ready.wait()

        async with self._lock:
            kc = self.kc
            if kc is None:
                return ExecResult(False, ename="KernelError", evalue="Kernel client is not ready")

            # Handle working directory change if requested
            if working_dir is not None:
                # Save current directory and change to requested directory
                chdir_code = f"""import os as _ipython_os
_ipython_prev_cwd = _ipython_os.getcwd()
_ipython_os.chdir({working_dir!r})
"""
                chdir_result = await self._execute_single(kc, chdir_code, timeout)
                if not chdir_result.ok:
                    # Restart kernel on failure to ensure recovery
                    await self._restart()
                    return chdir_result

            # Execute the actual user code
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
                async with asyncio.timeout(timeout):
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
            result = ExecResult(
                ok=ok,
                stdout="".join(stdout_chunks),
                result_repr=result_repr,
                ename=ename,
                evalue=evalue,
                traceback=tb_joined,
            )

            # Restore directory if it was changed
            if working_dir is not None:
                restore_code = """_ipython_os.chdir(_ipython_prev_cwd)
del _ipython_prev_cwd, _ipython_os
"""
                restore_result = await self._execute_single(kc, restore_code, timeout)
                # If restore fails, restart kernel and append warning
                if not restore_result.ok:
                    await self._restart()
                    if result.ok:
                        result.stdout += (
                            f"\nWarning: Failed to restore directory, kernel restarted: {restore_result.evalue}"
                        )

            return result

    async def _execute_single(self, kc, code: str, timeout: float) -> ExecResult:
        """Execute a single code snippet and wait for result (helper for directory changes)."""
        msg_id = kc.execute(code, store_history=False, allow_stdin=False, stop_on_error=True)

        stdout_chunks: list[str] = []
        ename: str | None = None
        evalue: str | None = None
        tb_joined: str | None = None
        got_idle = False
        got_reply = False

        async def drain_iopub() -> None:
            nonlocal stdout_chunks, ename, evalue, tb_joined, got_idle
            while True:
                msg = await kc.get_iopub_msg(timeout=timeout)
                if msg.get("parent_header", {}).get("msg_id") != msg_id:
                    continue
                msg_type = msg["msg_type"]
                content = msg["content"]
                if msg_type == "status" and content.get("execution_state") == "idle":
                    got_idle = True
                    return
                if msg_type == "stream" and content.get("name") in ("stdout", "stderr"):
                    stdout_chunks.append(content.get("text", ""))
                elif msg_type == "error":
                    ename = content.get("ename")
                    evalue = content.get("evalue")
                    traceback_list = content.get("traceback") or []
                    tb_joined = "\n".join(traceback_list)

        async def wait_shell_reply() -> None:
            nonlocal got_reply
            for _ in range(100):
                reply = await kc.get_shell_msg(timeout=timeout)
                if reply.get("parent_header", {}).get("msg_id") == msg_id:
                    got_reply = True
                    return
            raise RuntimeError("Failed to receive shell reply")

        try:
            async with asyncio.timeout(timeout):
                await asyncio.gather(drain_iopub(), wait_shell_reply())
        except TimeoutError:
            return ExecResult(False, ename="TimeoutError", evalue=f"Timeout after {timeout}s")
        except Exception as exc:
            return ExecResult(False, ename=exc.__class__.__name__, evalue=str(exc))

        ok = got_idle and got_reply and ename is None
        return ExecResult(ok=ok, stdout="".join(stdout_chunks), ename=ename, evalue=evalue, traceback=tb_joined)

    async def _apply_nest_asyncio(self, kc) -> None:
        """Enable nested event loops inside the kernel so asyncio.run works post-restart."""
        nest_asyncio_code = "import nest_asyncio; nest_asyncio.apply()"
        await self._execute_single(kc, nest_asyncio_code, timeout=10.0)


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

    async def execute(
        self, client_id: str, code: str, timeout: float = DEFAULT_TIMEOUT_SECONDS, working_dir: str | None = None
    ) -> ExecResult:
        session = await self.get_or_create(client_id)
        return await session.execute(code, timeout=timeout, working_dir=working_dir)

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


class IPythonInterpreter(BaseTool):  # type: ignore[misc]
    """
    A persistent IPython-style interpreter tool with access to the internet and file system.

    Executes Python code in an isolated, persistent shell stored in shared context.
    Variables and imports persist across executions for the same agent/session.
    """

    code: str = Field(
        ..., description="Python code to execute (multi-line supported, separated with newline character)."
    )
    working_dir: str | None = Field(
        None,
        description=(
            "Optional directory path to execute code in. Accepts both absolute and relative paths."
            "The tool will change to this directory before execution and restore the previous directory afterward."
        ),
    )
    timeout: float = Field(
        DEFAULT_TIMEOUT_SECONDS,
        description="Maximum execution time in seconds. Code execution will be interrupted if it exceeds this limit.",
    )

    async def run(self) -> str:
        agent_name = None
        if self._caller_agent and hasattr(self._caller_agent, "name"):
            agent_name = self._caller_agent.name
        elif self.context:
            agent_name = self.context.current_agent_name

        result: ExecResult
        session: AsyncKernelSession | None = None
        timeout_value = self.timeout
        fields_set: set[str] = getattr(self, "model_fields_set", set())
        if "timeout" not in fields_set:
            config_timeout = getattr(self.ToolConfig, "kernel_timeout_seconds", None)
            if config_timeout is not None:
                timeout_value = config_timeout

        try:
            if self.context and agent_name:
                pool: AsyncKernelPool | None = self.context.get("ipython_kernel_pool")
                if pool is None:
                    pool = AsyncKernelPool()
                    self.context.set("ipython_kernel_pool", pool)
                result = await pool.execute(
                    agent_name,
                    self.code,
                    timeout=timeout_value,
                    working_dir=self.working_dir,
                )
            else:
                # Fallback: create ephemeral kernel for this execution
                session = AsyncKernelSession()
                await session.start()
                result = await session.execute(
                    self.code,
                    timeout=timeout_value,
                    working_dir=self.working_dir,
                )
        finally:
            if session is not None:
                await session.shutdown()

        if not result.ok:
            details = result.traceback or ""
            if not details and result.evalue:
                if result.ename:
                    details = f"{result.ename}: {result.evalue}"
                else:
                    details = result.evalue
            if not details:
                details = "Kernel execution failed"
            return f"Error:\n{details}"

        parts = []
        stdout = result.stdout.strip()
        if stdout:
            parts.append(f"Output:\n{stdout}")
        if result.result_repr:
            parts.append(f"Result: {result.result_repr}")

        return "\n\n".join(parts) if parts else "Executed successfully (no output)."
