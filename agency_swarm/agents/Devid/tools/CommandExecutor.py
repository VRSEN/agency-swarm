from agency_swarm.tools import BaseTool
from pydantic import Field
import subprocess
import shlex
from dotenv import load_dotenv, find_dotenv

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
        load_dotenv(find_dotenv() or None)
        # Ensure the command is safely split for subprocess
        command_parts = shlex.split(self.command)

        # Execute the command and capture the output
        result = subprocess.run(command_parts, capture_output=True, text=True)

        # check if the command failed
        if result.returncode != 0 or result.stderr:
            return (f"stdout: {result.stdout}\nstderr: {result.stderr}\nexit code: {result.returncode}\n\n"
                    f"Please add error handling and continue debugging until the command runs successfully.")

        return f"stdout: {result.stdout}\nstderr: {result.stderr}\nexit code: {result.returncode}"

if __name__ == "__main__":
    tool = CommandExecutor(command="ls -l")
    print(tool.run())
