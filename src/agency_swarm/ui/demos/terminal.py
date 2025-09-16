from collections.abc import Generator


def start_terminal(agency_instance, show_reasoning: bool = False) -> None:
    """Run the terminal demo: input loop, slash commands, and streaming output."""
    import asyncio
    import logging
    import os
    import re
    import uuid

    from ..core.console_event_adapter import ConsoleEventAdapter

    # Late import to avoid circulars and keep launcher small
    TerminalDemoLauncher = __import__(
        "agency_swarm.ui.demos.launcher", fromlist=["TerminalDemoLauncher"]
    ).TerminalDemoLauncher

    logger = logging.getLogger(__name__)

    recipient_agents = [str(agent.name) for agent in agency_instance.entry_points]
    if not recipient_agents:
        raise ValueError("Cannot start terminal demo without entry points. Please specify at least one entry point.")

    chat_id = f"run_demo_chat_{uuid.uuid4()}"

    event_converter = ConsoleEventAdapter(show_reasoning=show_reasoning)
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
        if cmd == "reset":
            cmd = "clear"
        return cmd, args

    def _print_help() -> None:
        rows = [
            ("/help", "Show help"),
            ("/clear (reset)", "Clear conversation history and free up context"),
            ("/compact [instructions]", "Keep a summary in context (optional custom prompt)"),
            ("/resume", "Resume a conversation"),
            ("/status", "Show current setup"),
            ("/exit (quit)", "Quit"),
        ]
        for cmd, desc in rows:
            event_converter.console.print(f"[cyan]{cmd}[/cyan]  {desc}")
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
            if cmd in {"clear"}:
                TerminalDemoLauncher.save_current_chat(agency_instance, chat_id)
                agency_instance.thread_manager.clear()
                chat_id = f"run_demo_chat_{uuid.uuid4()}"
                event_converter.console.print("Started a new chat session.")
                event_converter.console.rule()
                return False
            if cmd == "resume":
                chosen = TerminalDemoLauncher.resume_interactive(
                    agency_instance, input_func=input, print_func=event_converter.console.print
                )
                if chosen:
                    chat_id = chosen
                    event_converter.console.print(f"Resumed chat: {chat_id}")
                event_converter.console.rule()
                return False
            if cmd == "status":
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
                return False
            if cmd == "compact":
                chat_id = await TerminalDemoLauncher.compact_thread(agency_instance, args)
                event_converter.console.print("Conversation compacted. A system summary has been added.")
                event_converter.console.rule()
                return False
            if cmd == "exit":
                return True

        recipient_agent = None
        agent_mention_pattern = r"(?:^|\s)@(\w+)(?:\s|$)"
        agent_match = re.search(agent_mention_pattern, message)

        if agent_match:
            mentioned_agent = agent_match.group(1)
            try:
                recipient_agent = [agent for agent in recipient_agents if agent.lower() == mentioned_agent.lower()][0]
                message = re.sub(agent_mention_pattern, " ", message).strip()
            except Exception:
                logger.error(f"Recipient agent {mentioned_agent} not found.", exc_info=True)
                return False

        if recipient_agent is None and agency_instance.entry_points:
            recipient_agent = current_default_recipient

        try:
            response_buffer = ""
            recipient_agent_str: str = recipient_agent if recipient_agent is not None else current_default_recipient
            async for event in agency_instance.get_response_stream(
                message=message,
                recipient_agent=recipient_agent_str,
                chat_id=chat_id,
            ):
                event_converter.openai_to_message_output(event, recipient_agent_str)
                if hasattr(event, "data") and getattr(event.data, "type", None) == "response.output_text.delta":
                    response_buffer += event.data.delta
            event_converter.console.rule()
            TerminalDemoLauncher.save_current_chat(agency_instance, chat_id)
        except Exception as e:
            logger.error(f"Error during streaming: {e}", exc_info=True)
        return False

    async def main_loop():
        try:
            from prompt_toolkit import PromptSession
            from prompt_toolkit.completion import Completer, Completion
            from prompt_toolkit.history import InMemoryHistory
            from prompt_toolkit.key_binding import KeyBindings
        except Exception:
            PromptSession = None  # type: ignore

        if PromptSession is not None:
            command_help: dict[str, str] = {
                "/help": "Show help",
                "/clear": "Clear conversation and free context",
                "/compact": "Keep a summary in context",
                "/resume": "Resume a conversation",
                "/status": "Show current setup",
                "/exit": "Quit",
            }

            command_display_overrides: dict[str, str] = {
                "/exit": "/exit (quit)",
                "/clear": "/clear (reset)",
                "/compact": "/compact [instructions]",
                "/resume": "/resume",
            }

            class SlashCompleter(Completer):  # type: ignore[misc]
                def get_completions(self, document, complete_event) -> Generator[Completion]:  # type: ignore[override]
                    text = document.text_before_cursor
                    if not text or not text.startswith("/"):
                        return
                    if text == "/":
                        entries = list(command_help.keys())
                    else:
                        entries = [c for c in command_help.keys() if c.startswith(text)]
                    for cmd in entries:
                        display = command_display_overrides.get(cmd, cmd)
                        yield Completion(
                            text=cmd,
                            start_position=-len(text),
                            display=display,
                            display_meta=command_help[cmd],
                        )

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

            try:
                session = PromptSession(
                    history=history,
                    key_bindings=bindings,
                    enable_history_search=True,
                    mouse_support=False,
                )
            except Exception:
                PromptSession = None
                session = None

            if PromptSession is not None and session is not None:
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
                    except Exception:
                        PromptSession = None
                        break

                    event_converter.console.rule()
                    should_exit = await handle_message(message)
                    if should_exit:
                        return

        # Fallback basic input
        while True:
            message = input("👤 USER: ")
            event_converter.console.rule()
            should_exit = await handle_message(message)
            if should_exit:
                return

    try:
        asyncio.run(main_loop())
    except (KeyboardInterrupt, EOFError):
        print("\n\nExiting terminal demo...")
