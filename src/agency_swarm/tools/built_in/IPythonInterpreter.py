# ipython_interpreter.py
import contextlib
import traceback
from io import StringIO

from IPython.core.interactiveshell import InteractiveShell
from pydantic import Field

from agency_swarm.tools import BaseTool


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
        # Retrieve or create persistent shell from shared context
        shell = None
        if self._shared_state is not None:
            shell = self._shared_state.get("ipython_shell")
        print(f"shell: {shell}")
        if shell is None:
            shell = InteractiveShell.instance()
            if self._shared_state is not None:
                self._shared_state.set("ipython_shell", shell)

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
