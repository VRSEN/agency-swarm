# local_shell_tool.py
import os
import subprocess
import sys

from pydantic import Field

from agency_swarm.tools.base_tool import BaseTool


class PersistentShellTool(BaseTool):  # type: ignore[misc]
    """
    Execute shell commands locally with persistent working directory.

    Allows the agent to run any shell commands like bash, file operations,
    package installations, etc. The working directory persists across commands
    within the same session.
    """

    command: str = Field(..., description="Shell command to execute (e.g., 'ls -la', 'cat file.txt')")

    async def run(self) -> str:
        """
        Execute the shell command and return output.
        """
        cwd = os.getcwd()  # Default working directory

        # Get agent identifier for isolation
        agent_name = None
        if self._caller_agent and hasattr(self._caller_agent, "name"):
            agent_name = self._caller_agent.name
        elif self.context:
            agent_name = self.context.current_agent_name

        try:
            # Get persistent working directory from shared state, keyed by agent name
            if self.context and agent_name:
                cwds_dict = self.context.get("shell_cwds", {})
                cwd = cwds_dict.get(agent_name)
                if cwd is None:
                    cwd = os.getcwd()
                    cwds_dict[agent_name] = cwd
                    self.context.set("shell_cwds", cwds_dict)
            else:
                # If context or agent name is not available, use current directory
                cwd = os.getcwd()

            # Execute command
            # Use PowerShell on Windows for better compatibility (supports ~, etc.)
            if sys.platform == "win32":
                result = subprocess.run(
                    ["powershell", "-Command", self.command],
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=300,  # 5 minute timeout
                )
            else:
                result = subprocess.run(
                    self.command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=300,  # 5 minute timeout
                )

            # Update working directory if cd command was used and succeeded
            # Only track standalone cd commands, not chained commands (cd dir && cmd)
            cd_warning = None
            cmd_stripped = self.command.strip()
            if cmd_stripped.startswith("cd ") and result.returncode == 0:
                # Check if this is a chained command (contains &&, ||, ;, |)
                if any(op in self.command for op in ["&&", "||", ";", "|"]):
                    cd_warning = (
                        "Warning: cd in chained command not persisted. "
                        "Use separate cd command to change working directory permanently."
                    )
                else:
                    # Parse the new directory (everything after "cd ")
                    new_dir = cmd_stripped[3:].strip()
                    if new_dir:
                        # Remove surrounding quotes if present
                        if (new_dir.startswith('"') and new_dir.endswith('"')) or (
                            new_dir.startswith("'") and new_dir.endswith("'")
                        ):
                            new_dir = new_dir[1:-1]

                        # Expand ~ to home directory
                        new_dir = os.path.expanduser(new_dir)

                        # Expand environment variables like $HOME
                        new_dir = os.path.expandvars(new_dir)

                        # Resolve relative paths
                        if not os.path.isabs(new_dir):
                            new_dir = os.path.join(cwd, new_dir)
                        new_dir = os.path.abspath(new_dir)

                        # Update if directory exists
                        if os.path.isdir(new_dir):
                            if self.context and agent_name:
                                cwds_dict = self.context.get("shell_cwds", {})
                                cwds_dict[agent_name] = new_dir
                                self.context.set("shell_cwds", cwds_dict)
                            cwd = new_dir

            # Format output
            output_parts = []

            if result.stdout:
                output_parts.append(f"**Output:**\n```\n{result.stdout.strip()}\n```")

            if result.stderr:
                output_parts.append(f"**Stderr:**\n```\n{result.stderr.strip()}\n```")

            if result.returncode != 0:
                output_parts.append(f"**Exit Code:** {result.returncode}")

            if not output_parts:
                output_parts.append("✅ Command executed successfully (no output)")

            output = "\n\n".join(output_parts)

            if cd_warning:
                output += f"\n\n**Warning:** {cd_warning}"

            output += f"\n\n**Working Directory:** `{cwd}`"

            return output

        except subprocess.TimeoutExpired:
            return f"❌ Error: Command timed out after 5 minutes\n\n**Working Directory:** `{cwd}`"
        except Exception as e:
            return f"❌ Error executing command: {str(e)}\n\n**Working Directory:** `{cwd}`"
