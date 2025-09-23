import asyncio
import logging
import os
import re
from collections.abc import Generator
from typing import Any, cast

import prompt_toolkit as prompt_toolkit
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings

from agency_swarm.agency.core import Agency

from ..core.console_event_adapter import ConsoleEventAdapter
from .launcher import TerminalDemoLauncher


def start_terminal(
    agency_instance: Agency,
    show_reasoning: bool = False,
) -> None:
    """Run the terminal demo: input loop, slash commands, and streaming output."""
    logger = logging.getLogger(__name__)

    recipient_agents = [str(agent.name) for agent in agency_instance.entry_points]
    if not recipient_agents:
        raise ValueError("Cannot start terminal demo without entry points. Please specify at least one entry point.")

    chat_id = TerminalDemoLauncher.start_new_chat(agency_instance)

    event_converter = ConsoleEventAdapter(
        show_reasoning=show_reasoning,
        agents=list(agency_instance.agents.keys()),
    )
    event_converter.console.rule()
    try:
        cwd = os.getcwd()
        banner_name = getattr(agency_instance, "name", None) or "Agency Swarm"
        event_converter.console.print(f"[bold]* Welcome to {banner_name}![/bold]")
        event_converter.console.print("\n/help for help, /status for your current setup\n")
        event_converter.console.print(f"cwd: {cwd}\n")
        event_converter.console.rule()
    except Exception:
        pass

    current_default_recipient = agency_instance.entry_points[0].name

    def _parse_slash_command(text: str) -> tuple[str, list[str]] | None:
        if not text:
            return None
        stripped = text.strip()
        if not stripped.startswith("/"):
            return None
        if stripped == "/":
            return ("help", [])
        parts = stripped[1:].split()
        if not parts:
            return None
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd in {"quit", "exit"}:
            cmd = "exit"
        return cmd, args

    def _print_help() -> None:
        rows = [
            ("/help", "Show help"),
            ("/new", "Start a new chat"),
            ("/compact [instructions]", "Summarize and continue"),
            ("/resume", "Resume a conversation"),
            ("/status", "Show current setup"),
            ("/exit (quit)", "Quit"),
        ]
        for cmd, desc in rows:
            event_converter.console.print(f"[cyan]{cmd}[/cyan]  {desc}")
        event_converter.console.rule()

    def _start_new_chat() -> None:
        """Start a chat session with a fresh chat id."""
        nonlocal chat_id
        chat_id = TerminalDemoLauncher.start_new_chat(agency_instance)
        event_converter.console.print("Started a new chat session.")
        event_converter.console.rule()
        event_converter.handoff_agent = None

    def _resume_chat() -> None:
        """Load a previously saved chat into context."""
        nonlocal chat_id
        chosen = TerminalDemoLauncher.resume_interactive(
            agency_instance, input_func=input, print_func=event_converter.console.print
        )
        if chosen:
            chat_id = chosen
            event_converter.console.print(f"Resumed chat: {chat_id}")
        event_converter.console.rule()
        # Restore last non-default assistant speaker as active handoff recipient
        try:
            message_history = agency_instance.thread_manager.get_all_messages()
            event_converter.handoff_agent = None
            for message in reversed(message_history):
                if not isinstance(message, dict):
                    continue
                msg_dict = cast(dict[str, Any], message)
                if (
                    msg_dict.get("type") == "message"
                    and msg_dict.get("role") == "assistant"
                    and msg_dict.get("callerAgent") is None
                ):
                    agent = msg_dict.get("agent")
                    if isinstance(agent, str) and agent != current_default_recipient:
                        event_converter.handoff_agent = agent
                    else:
                        event_converter.handoff_agent = None
                    break
        except Exception:
            # Non-fatal; resume continues without restoring handoff
            event_converter.handoff_agent = None

    def _print_status() -> None:
        """Display current agency metadata and defaults."""
        _cwd = os.getcwd()
        meta = {
            "Agency": getattr(agency_instance, "name", None) or "Unnamed Agency",
            "Entry Points": ", ".join([a.name for a in agency_instance.entry_points]) or "None",
            "Default Recipient": current_default_recipient or "None",
            "cwd": _cwd,
        }
        for k, v in meta.items():
            event_converter.console.print(f"[bold]{k}[/bold]: {v}")
        event_converter.console.rule()

    async def _compact_chat(args: list[str]) -> None:
        """Summarize the current conversation and continue with a fresh chat id."""
        nonlocal chat_id
        chat_id = await TerminalDemoLauncher.compact_thread(agency_instance, args)
        event_converter.console.print("Conversation compacted. A system summary has been added.")
        event_converter.console.rule()

    async def handle_message(message: str) -> bool:  # noqa: C901
        nonlocal chat_id, current_default_recipient
        if not message:
            return False

        parsed = _parse_slash_command(message)
        if parsed is not None:
            cmd, args = parsed
            if cmd == "help":
                _print_help()
                return False
            if cmd in {"new"}:
                _start_new_chat()
                return False
            if cmd == "resume":
                _resume_chat()
                return False
            if cmd == "status":
                _print_status()
                return False
            if cmd == "compact":
                await _compact_chat(args)
                return False
            if cmd == "exit":
                return True

        recipient_agent = None
        agent_mention_pattern = r"(?:^|\s)@(\w+)(?:\s|$)"
        agent_match = re.search(agent_mention_pattern, message)

        if message.startswith("@"):
            mentioned_agent = agent_match.group(1) if agent_match is not None else None
            for agent in recipient_agents:
                if message.lower().startswith(f"@{agent.lower()}"):
                    recipient_agent = agent
                    message = message[len(f"@{agent.lower()}") :].strip()
                    break
            if recipient_agent is None:
                logger.error(f"Recipient agent {mentioned_agent or 'Unknown'} not found.", exc_info=True)
                return False

        # Clear handoff to correctly display recipient when an explicit target is used
        if recipient_agent is not None and recipient_agent != event_converter.handoff_agent:
            event_converter.handoff_agent = None

        try:
            recipient_agent_str: str = (
                recipient_agent
                if recipient_agent is not None
                else event_converter.handoff_agent
                if event_converter.handoff_agent is not None
                else current_default_recipient
            )
            async for event in agency_instance.get_response_stream(
                message=message,
                recipient_agent=recipient_agent_str,
                chat_id=chat_id,
            ):
                event_converter.openai_to_message_output(event, recipient_agent_str)
            event_converter.console.rule()
            TerminalDemoLauncher.save_current_chat(agency_instance, chat_id)
        except Exception as e:
            logger.error(f"Error during streaming: {e}", exc_info=True)
        return False

    async def main_loop():
        # prompt_toolkit is a mandatory dependency; imported at module load

        command_help: dict[str, str] = {
            "/help": "Show help",
            "/new": "Start a new chat",
            "/compact": "Keep a summary in context",
            "/resume": "Resume a conversation",
            "/status": "Show current setup",
            "/exit": "Quit",
        }

        command_display_overrides: dict[str, str] = {
            "/exit": "/exit (quit)",
            "/new": "/new",
            "/compact": "/compact [instructions]",
            "/resume": "/resume",
        }

        class SlashCompleter(Completer):
            def get_completions(self, document, complete_event) -> Generator[Completion]:
                text = document.text_before_cursor
                if not text or not text.startswith("/"):
                    return
                key = text
                entries = list(command_help.keys()) if key == "/" else [c for c in command_help if c.startswith(key)]
                for cmd in entries:
                    display = command_display_overrides.get(cmd, cmd)
                    yield Completion(
                        text=cmd,
                        start_position=-len(key),
                        display=display,
                        display_meta=command_help[cmd],
                    )

        # Provide slash command suggestions only
        completer = SlashCompleter()
        history = InMemoryHistory()
        bindings = KeyBindings()

        @bindings.add("c-c")
        def _(event) -> None:
            event.app.exit(exception=KeyboardInterrupt)

        @bindings.add("/")
        def _(event) -> None:
            buf = event.app.current_buffer
            buf.insert_text("/")
            buf.start_completion(select_first=True)

        session = prompt_toolkit.PromptSession(
            history=history,
            key_bindings=bindings,
            enable_history_search=True,
            mouse_support=False,
        )

        while True:
            try:
                message = await session.prompt_async(
                    "👤 USER: ",
                    completer=completer,
                    complete_while_typing=True,
                    reserve_space_for_menu=8,
                )
            except (KeyboardInterrupt, EOFError):
                return

            event_converter.console.rule()
            should_exit = await handle_message(message)
            if should_exit:
                return

    try:
        asyncio.run(main_loop())
    except (KeyboardInterrupt, EOFError):
        print("\n\nExiting terminal demo...")
