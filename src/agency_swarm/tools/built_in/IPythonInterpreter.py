# ipython_interpreter.py
from __future__ import annotations

from typing import ClassVar

from pydantic import Field

from agency_swarm.tools.base_tool import BaseTool

from .ipython_kernel import AsyncKernelPool, AsyncKernelSession, ExecResult


class IPythonInterpreter(BaseTool):
    """
    A persistent IPython-style interpreter tool with access to the internet and file system.

    Executes Python code in an isolated, persistent shell stored in shared context.
    Variables and imports persist across executions for the same agent/session.
    """

    code: str = Field(
        ..., description="Python code to execute (multi-line supported, separated with newline character)."
    )

    DEFAULT_TIMEOUT_SECONDS: ClassVar[float] = 10.0

    async def run(self) -> str:
        agent_name = None
        if self._caller_agent and hasattr(self._caller_agent, "name"):
            agent_name = self._caller_agent.name
        elif self.context:
            agent_name = self.context.current_agent_name

        timeout = getattr(self.ToolConfig, "kernel_timeout_seconds", self.DEFAULT_TIMEOUT_SECONDS)
        result: ExecResult
        session: AsyncKernelSession | None = None

        try:
            if self.context and agent_name:
                pool: AsyncKernelPool | None = self.context.get("ipython_kernel_pool")
                if pool is None:
                    pool = AsyncKernelPool()
                    self.context.set("ipython_kernel_pool", pool)
                result = await pool.execute(agent_name, self.code, timeout=timeout)
            else:
                # Fallback: create ephemeral kernel for this execution
                session = AsyncKernelSession()
                await session.start()
                result = await session.execute(self.code, timeout=timeout)
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
