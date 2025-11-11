# ipython_interpreter.py
import contextlib
import traceback
from io import StringIO

from IPython.core.interactiveshell import InteractiveShell
from pydantic import Field

from agency_swarm.tools.base_tool import BaseTool


class IPythonInterpreter(BaseTool):
    """
    A persistent IPython-style interpreter tool with access to the internet and file system.

    Executes Python code in an isolated, persistent shell stored in shared context.
    Variables and imports persist across executions for the same agent/session.
    """

    code: str = Field(
        ..., description="Python code to execute (multi-line supported, separated with newline character)."
    )

    async def run(self) -> str:
        # Retrieve or create persistent shell from shared context, keyed by agent name
        shell = None

        # Get agent identifier for isolation
        agent_name = None
        if self._caller_agent and hasattr(self._caller_agent, "name"):
            agent_name = self._caller_agent.name
        elif self.context:
            agent_name = self.context.current_agent_name

        if self.context and agent_name:
            # Store shells in a dict keyed by agent name for per-agent isolation
            shells_dict = self.context.get("ipython_shells", {})
            shell = shells_dict.get(agent_name)

            if shell is None:
                # Create a new isolated shell instance for this agent
                shell = InteractiveShell()
                shells_dict[agent_name] = shell
                self.context.set("ipython_shells", shells_dict)
        else:
            # Fallback: create a new shell per execution (not persistent)
            # This happens if we can't identify the agent
            shell = InteractiveShell()

        output = StringIO()
        error = None

        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            try:
                result = shell.run_cell(self.code, store_history=True)
                if result.error_in_exec:
                    error = "".join(traceback.format_exception_only(type(result.error_in_exec), result.error_in_exec))
            except Exception as e:
                error = "".join(traceback.format_exception_only(type(e), e))

        stdout = output.getvalue().strip()

        if error:
            return f":x: Error:\n{error}"
        elif stdout:
            return f":white_check_mark: Output:\n{stdout}"
        elif hasattr(result, "result") and result.result is not None:
            return f":white_check_mark: Result: {repr(result.result)}"
        else:
            return ":white_check_mark: Executed successfully (no output)."
