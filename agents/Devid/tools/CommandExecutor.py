from agency_swarm.tools import BaseTool
from pydantic import Field
import subprocess
import shlex

class CommandExecutor(BaseTool):
    """
    Executes a specified command in the terminal and captures the output.

    This tool runs a given command in the system's default shell and returns the stdout and stderr.
    """

    command: str = Field(
        ..., description="The command to execute in the terminal."
    )

    def run(self):
        """
        Executes the command and captures its output.

        Returns:
            A dictionary containing the standard output (stdout), standard error (stderr),
            and the exit code of the command.
        """
        # Ensure the command is safely split for subprocess
        command_parts = shlex.split(self.command)

        # Execute the command and capture the output
        result = subprocess.run(command_parts, capture_output=True, text=True)

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }

if __name__ == "__main__":
    tool = ExecuteTerminalCommand(command="ls -l")
    print(tool.run())
