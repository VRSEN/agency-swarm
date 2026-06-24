"""Default replacements for OpenAI hosted tools on incompatible backends."""

from __future__ import annotations

import dataclasses
import inspect
import json
import os
import shlex
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from agents import (
    FunctionTool,
    LocalShellCommandRequest,
    LocalShellTool,
    RunContextWrapper,
    ShellActionRequest,
    ShellCallData,
    ShellCommandRequest,
    ShellResult,
    ShellTool,
    Tool,
)
from agents.mcp.server import MCPServer

from agency_swarm.tools.base_tool import BaseTool
from agency_swarm.tools.tool_factory import ToolFactory

EXA_MCP_BASE_URL = "https://mcp.exa.ai/mcp"
EXA_SEARCH_SERVER_NAME = "Exa_Search"
_EXA_ALLOWED_TOOL_NAMES = ("web_search_exa", "web_fetch_exa")
_BUILTIN_REPLACEMENT_TOOL_NAMES = frozenset({"web_search", "code_interpreter", "local_shell", "shell"})
_LOCAL_SHELL_PARAMS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {
            "anyOf": [
                {"type": "array", "items": {"type": "string"}},
                {"type": "string"},
            ],
            "description": "Argv tokens or a shell command string.",
        },
        "commands": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Shell command strings (first non-empty entry is used).",
        },
        "env": {
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        "working_directory": {"type": "string"},
        "timeout_ms": {"type": "integer"},
        "user": {"type": "string"},
    },
    "additionalProperties": False,
}
_SHELL_PARAMS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "commands": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Shell command strings to run in order.",
        },
        "command": {
            "anyOf": [
                {"type": "array", "items": {"type": "string"}},
                {"type": "string"},
            ],
            "description": "Single shell command as a string or argv tokens.",
        },
        "timeout_ms": {"type": "integer"},
        "max_output_length": {"type": "integer"},
    },
    "additionalProperties": False,
}


@dataclass
class _CompatLocalShellAction:
    """Action payload exposing both local_shell and shell field names for executors."""

    command: list[str]
    commands: list[str]
    env: dict[str, str]
    type: Literal["exec"] = "exec"
    working_directory: str | None = None
    timeout_ms: int | None = None
    user: str | None = None


@dataclass
class _CompatLocalShellCall:
    action: _CompatLocalShellAction
    id: str = "local_shell_replacement"
    call_id: str = "local_shell_replacement"
    type: Literal["local_shell_call"] = "local_shell_call"
    status: Literal["in_progress", "completed", "incomplete"] = "in_progress"


class _McpServerOwner(Protocol):
    mcp_servers: list[MCPServer]


def has_builtin_hosted_tool_replacement(name: str) -> bool:
    return name in _BUILTIN_REPLACEMENT_TOOL_NAMES


def build_exa_search_server() -> MCPServer:
    from agents.mcp import MCPServerStreamableHttp

    return MCPServerStreamableHttp(
        name=EXA_SEARCH_SERVER_NAME,
        params={"url": EXA_MCP_BASE_URL},
        cache_tools_list=True,
        client_session_timeout_seconds=30,
        tool_filter={"allowed_tool_names": list(_EXA_ALLOWED_TOOL_NAMES)},
    )


def ensure_exa_search_server(agent: _McpServerOwner) -> None:
    if not isinstance(agent.mcp_servers, list):
        agent.mcp_servers = []
    servers = agent.mcp_servers
    if any(getattr(server, "name", None) == EXA_SEARCH_SERVER_NAME for server in servers):
        return
    servers.append(build_exa_search_server())


def has_exa_search_server(agent: object) -> bool:
    servers = getattr(agent, "mcp_servers", None)
    if not isinstance(servers, list):
        return False
    return any(getattr(server, "name", None) == EXA_SEARCH_SERVER_NAME for server in servers)


def _adapt_base_tool_as(base_tool: type[BaseTool], name: str) -> FunctionTool:
    return dataclasses.replace(ToolFactory.adapt_base_tool(base_tool), name=name)


def _build_code_interpreter_replacement() -> FunctionTool | None:
    try:
        from agency_swarm.tools.built_in.IPythonInterpreter import IPythonInterpreter
    except ImportError:
        return None
    return _adapt_base_tool_as(IPythonInterpreter, "code_interpreter")


def _build_persistent_shell_replacement(name: str) -> FunctionTool:
    from agency_swarm.tools.built_in.PersistentShellTool import PersistentShellTool

    return _adapt_base_tool_as(PersistentShellTool, name)


def _build_local_shell_persistent_replacement() -> FunctionTool:
    return _build_persistent_shell_replacement("local_shell")


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _split_shell_command(command: str) -> list[str]:
    stripped = command.strip()
    if not stripped:
        return []
    return shlex.split(stripped, posix=os.name != "nt")


def _resolve_shell_command(payload: dict[str, Any]) -> list[str]:
    command_value = payload.get("command")
    if isinstance(command_value, list):
        tokens = [str(entry) for entry in command_value if entry is not None and str(entry)]
        if tokens:
            return tokens
    if isinstance(command_value, str):
        tokens = _split_shell_command(command_value)
        if tokens:
            return tokens

    commands_value = payload.get("commands")
    if isinstance(commands_value, list):
        for entry in commands_value:
            if isinstance(entry, str):
                tokens = _split_shell_command(entry)
                if tokens:
                    return tokens
    return []


def _resolve_local_shell_action(payload: dict[str, Any]) -> _CompatLocalShellAction | None:
    shell_commands = _resolve_shell_commands(payload)
    argv = _resolve_shell_command(payload)

    if shell_commands and not argv:
        argv = _split_shell_command(shell_commands[0])
    if argv and not shell_commands:
        shell_commands = [" ".join(argv)]
    if not argv or not shell_commands:
        return None

    env_value = payload.get("env")
    env = (
        {str(key): str(value) for key, value in env_value.items()}
        if isinstance(env_value, dict)
        else {}
    )
    return _CompatLocalShellAction(
        command=argv,
        commands=shell_commands,
        env=env,
        working_directory=_optional_str(payload.get("working_directory")),
        timeout_ms=_optional_int(payload.get("timeout_ms")),
        user=_optional_str(payload.get("user")),
    )


def _resolve_shell_commands(payload: dict[str, Any]) -> list[str]:
    commands_value = payload.get("commands")
    if isinstance(commands_value, list):
        commands = [str(entry).strip() for entry in commands_value if entry is not None and str(entry).strip()]
        if commands:
            return commands

    command_value = payload.get("command")
    if isinstance(command_value, str):
        stripped = command_value.strip()
        if stripped:
            return [stripped]
    if isinstance(command_value, list):
        tokens = [str(entry) for entry in command_value if entry is not None and str(entry)]
        if tokens:
            return [" ".join(tokens)]
    return []


def _format_shell_executor_result(result: str | ShellResult) -> str:
    if isinstance(result, ShellResult):
        chunks: list[str] = []
        for entry in result.output:
            if entry.stdout:
                chunks.append(entry.stdout)
            if entry.stderr:
                chunks.append(entry.stderr)
        return "\n".join(chunks) or "(no output)"
    return str(result)


def _shell_tool_uses_local_executor(hosted_tool: ShellTool) -> bool:
    environment = hosted_tool.environment
    if not isinstance(environment, dict):
        return True
    return environment.get("type", "local") == "local"


def _build_shell_executor_replacement(hosted_tool: ShellTool) -> FunctionTool:
    if hosted_tool.executor is None:
        raise TypeError("ShellTool requires a local executor for shell replacement.")
    executor = hosted_tool.executor
    tool_name = hosted_tool.name

    async def _invoke(ctx: RunContextWrapper[Any], input_json: str) -> str:
        try:
            payload = json.loads(input_json or "{}")
        except json.JSONDecodeError:
            return "Error: shell arguments must be valid JSON."

        if not isinstance(payload, dict):
            payload = {}

        commands = _resolve_shell_commands(payload)
        if not commands:
            return "Error: shell requires at least one command."

        shell_call = ShellCallData(
            call_id="shell_replacement",
            action=ShellActionRequest(
                commands=commands,
                timeout_ms=_optional_int(payload.get("timeout_ms")),
                max_output_length=_optional_int(payload.get("max_output_length")),
            ),
            status="in_progress",
        )
        request = ShellCommandRequest(ctx_wrapper=ctx, data=shell_call)
        result = executor(request)
        if inspect.isawaitable(result):
            result = await result
        return _format_shell_executor_result(result)

    return FunctionTool(
        name=tool_name,
        description="Run shell commands through the agent's configured shell executor.",
        params_json_schema=_SHELL_PARAMS_JSON_SCHEMA,
        on_invoke_tool=_invoke,
        strict_json_schema=False,
    )


def _build_shell_replacement(hosted_tool: Tool | None) -> FunctionTool:
    tool_name = hosted_tool.name if isinstance(hosted_tool, ShellTool) else "shell"
    if (
        isinstance(hosted_tool, ShellTool)
        and callable(hosted_tool.executor)
        and _shell_tool_uses_local_executor(hosted_tool)
    ):
        return _build_shell_executor_replacement(hosted_tool)
    return _build_persistent_shell_replacement(tool_name)


def _build_local_shell_executor_replacement(hosted_tool: LocalShellTool) -> FunctionTool:
    executor = hosted_tool.executor

    async def _invoke(ctx: RunContextWrapper[Any], input_json: str) -> str:
        try:
            payload = json.loads(input_json or "{}")
        except json.JSONDecodeError:
            return "Error: local_shell arguments must be valid JSON."

        if not isinstance(payload, dict):
            payload = {}

        action = _resolve_local_shell_action(payload)
        if action is None:
            return "Error: local_shell requires a non-empty command."

        shell_call = _CompatLocalShellCall(action=action)
        request = LocalShellCommandRequest(
            ctx_wrapper=ctx,
            data=cast(Any, shell_call),
        )
        result = executor(request)
        if inspect.isawaitable(result):
            result = await result
        return str(result)

    return FunctionTool(
        name="local_shell",
        description="Run a shell command through the agent's configured local shell executor.",
        params_json_schema=_LOCAL_SHELL_PARAMS_JSON_SCHEMA,
        on_invoke_tool=_invoke,
        strict_json_schema=False,
    )


def _build_local_shell_replacement(hosted_tool: Tool | None) -> FunctionTool:
    if isinstance(hosted_tool, LocalShellTool) and callable(hosted_tool.executor):
        return _build_local_shell_executor_replacement(hosted_tool)
    return _build_local_shell_persistent_replacement()


def resolve_hosted_tool_replacement(
    agent: _McpServerOwner,
    name: str,
    *,
    hosted_tool: Tool | None = None,
) -> Tool | None:
    if name == "web_search":
        ensure_exa_search_server(agent)
        return None
    if name == "code_interpreter":
        return _build_code_interpreter_replacement()
    if name == "local_shell":
        return _build_local_shell_replacement(hosted_tool)
    if name == "shell":
        return _build_shell_replacement(hosted_tool)
    return None
