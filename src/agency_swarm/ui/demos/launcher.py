class CopilotDemoLauncher:
    @staticmethod
    def start(
        agency_instance,
        host: str = "0.0.0.0",
        port: int = 8000,
        frontend_port: int = 3000,
        cors_origins: list[str] | None = None,
    ):
        """Launch the Copilot UI demo with backend and frontend servers."""
        import atexit
        import os
        import shutil
        import subprocess
        from pathlib import Path

        from agency_swarm.integrations.fastapi import run_fastapi

        fe_path = Path(__file__).parent / "copilot"

        # Safety checks – ensure Node.js environment is ready
        npm_exe = shutil.which("npm") or shutil.which("npm.cmd")
        if npm_exe is None:
            raise RuntimeError(
                "npm was not found on your PATH. Install Node.js (https://nodejs.org) "
                "and ensure `npm` is accessible before running CopilotDemoLauncher."
            )

        if not (fe_path / "node_modules").exists():
            print(
                "\033[93m[Copilot Demo] 'node_modules' not found in copilot app directory. "
                "Running 'npm install' to install frontend dependencies...\033[0m"
            )
            try:
                subprocess.check_call([npm_exe, "install"], cwd=fe_path)
                print(
                    "\033[92m[Copilot Demo] Frontend dependencies installed successfully. "
                    "Frontend might take a few seconds to load.\033[0m"
                )
            except subprocess.CalledProcessError as e:
                raise RuntimeError(
                    f"Failed to install frontend dependencies in {fe_path}. Please check your npm setup and try again."
                ) from e

        # Before starting the frontend process
        os.environ["NEXT_PUBLIC_AG_UI_BACKEND_URL"] = (
            f"http://{host}:{port}/{getattr(agency_instance, 'name', None) or 'agency'}/get_response_stream/"
        )

        # Start the frontend
        proc = subprocess.Popen(
            [npm_exe, "run", "dev", "--", "-p", str(frontend_port)],
            cwd=fe_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        # Ensure we clean up on ^C / exit
        atexit.register(proc.terminate)
        print(
            f"\n\033[92;1m🚀  Copilot UI running at http://localhost:{frontend_port}\n"
            "    It might take a moment for the page to load the first time you open it.\033[0m\n"
        )

        # Start the backend
        run_fastapi(
            agencies={getattr(agency_instance, "name", None) or "agency": lambda **kwargs: agency_instance},
            host=host,
            port=port,
            app_token_env="",
            cors_origins=cors_origins,
            enable_agui=True,
        )


class TerminalDemoLauncher:
    @staticmethod
    def start(agency_instance):
        """
        Executes agency in the terminal with autocomplete for recipient agent names.
        """
        import asyncio
        import logging
        import os
        import re
        import uuid

        from ..core.console_event_adapter import ConsoleEventAdapter

        logger = logging.getLogger(__name__)

        recipient_agents = [str(agent.name) for agent in agency_instance.entry_points]
        if not recipient_agents:
            raise ValueError(
                "Cannot start terminal demo without entry points. Please specify at least one entry point."
            )

        chat_id = f"run_demo_chat_{uuid.uuid4()}"

        event_converter = ConsoleEventAdapter()
        event_converter.console.rule()
        # a welcome banner and hint line
        try:
            cwd = os.getcwd()
            banner_name = getattr(agency_instance, "name", None) or "Agency Swarm"
            event_converter.console.print(f"[bold]* Welcome to {banner_name}![/bold]")
            event_converter.console.print("\n/help for help, /status for your current setup\n")
            event_converter.console.print(f"cwd: {cwd}\n")
            event_converter.console.rule()
        except Exception:
            pass

        # Keep track of the current default recipient (first entry point by default)
        current_default_recipient = agency_instance.entry_points[0].name

        def _parse_slash_command(text: str):
            """Parse a leading slash command.

            Returns a tuple (cmd, args_list) or None if not a slash command.
            """
            if not text:
                return None
            stripped = text.strip()
            if not stripped.startswith("/"):
                return None
            # Single "/" shows help
            if stripped == "/":
                return ("help", [])
            parts = stripped[1:].split()
            if not parts:
                return None
            cmd = parts[0].lower()
            args = parts[1:]
            # normalize aliases
            if cmd in {"quit", "exit"}:
                cmd = "exit"
            if cmd == "reset":
                cmd = "clear"
            return cmd, args

        def _print_help():
            rows = [
                ("/help", "Show help"),
                ("/clear (reset)", "Clear conversation history and free up context"),
                ("/compact [instructions]", "Keep a summary in context (optional custom prompt)"),
                ("/status", "Show current setup"),
                ("/exit (quit)", "Quit"),
            ]
            for cmd, desc in rows:
                event_converter.console.print(f"[cyan]{cmd}[/cyan]  {desc}")
            event_converter.console.rule()

        async def main_loop():
            # Try enhanced interactive prompt with slash menu
            try:
                from prompt_toolkit import PromptSession
                from prompt_toolkit.completion import Completer, Completion
                from prompt_toolkit.history import InMemoryHistory
                from prompt_toolkit.key_binding import KeyBindings
            except Exception:
                PromptSession = None  # type: ignore

            async def handle_message(message: str) -> bool:
                """Process a single user message. Return True to exit, False to continue."""
                nonlocal chat_id, current_default_recipient
                if not message:
                    return False

                # Slash commands
                parsed = _parse_slash_command(message)
                if parsed is not None:
                    cmd, args = parsed
                    if cmd == "help":
                        _print_help()
                        return False
                    if cmd in {"clear"}:
                        agency_instance.thread_manager.clear()
                        chat_id = f"run_demo_chat_{uuid.uuid4()}"
                        event_converter.console.print("Started a new chat session.")
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
                        # Summarize using the current agent; no fallbacks, let errors surface
                        from agents import ModelSettings, RunConfig

                        all_messages = agency_instance.thread_manager.get_all_messages()

                        def _extract_text(content: object) -> str:
                            if isinstance(content, list):
                                parts: list[str] = []
                                for part in content:
                                    if isinstance(part, dict) and "text" in part:
                                        parts.append(str(part.get("text")))
                                if parts:
                                    return " ".join(parts)
                            return str(content)

                        transcript_lines: list[str] = []
                        for m in all_messages:
                            if not isinstance(m, dict):
                                continue
                            role_obj = m.get("role") or m.get("type")
                            role = str(role_obj) if role_obj is not None else ""
                            if role not in ("assistant", "system", "user"):
                                continue
                            if role == "assistant":
                                who = m.get("agent") or "assistant"
                            elif role == "user":
                                who = "user"
                            else:
                                who = "system"
                            content = _extract_text(m.get("content"))
                            if content:
                                transcript_lines.append(f"[{who}] {content}")
                        transcript = "\n".join(transcript_lines)

                        custom_instructions = " ".join(args) if args else ""
                        base_prompt = (
                            "Summarize the following conversation into a concise brief capturing goals, "
                            "decisions, facts, and actionable follow-ups. Use bullet points when helpful. "
                            "Keep it under 300 words."
                        )
                        final_prompt = (custom_instructions or base_prompt) + "\n\nConversation:\n" + transcript

                        rc = RunConfig(model="gpt-5-nano", model_settings=ModelSettings(temperature=0.0))
                        result = await agency_instance.get_response(message=final_prompt, run_config=rc)
                        summary_text = str(getattr(result, "final_output", "")).strip()

                        # Reset thread and seed summary as the only system message
                        agency_instance.thread_manager.clear()
                        chat_id = f"run_demo_chat_{uuid.uuid4()}"
                        agency_instance.thread_manager.add_message(
                            {
                                "role": "system",
                                "content": summary_text,
                            }
                        )

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
                        recipient_agent = [
                            agent for agent in recipient_agents if agent.lower() == mentioned_agent.lower()
                        ][0]
                        message = re.sub(agent_mention_pattern, " ", message).strip()
                    except Exception:
                        logger.error(f"Recipient agent {mentioned_agent} not found.", exc_info=True)
                        return False

                if recipient_agent is None and agency_instance.entry_points:
                    recipient_agent = current_default_recipient

                try:
                    response_buffer = ""
                    async for event in agency_instance.get_response_stream(
                        message=message,
                        recipient_agent=recipient_agent,
                        chat_id=chat_id,
                    ):
                        event_converter.openai_to_message_output(event, recipient_agent)
                        if hasattr(event, "data") and getattr(event.data, "type", None) == "response.output_text.delta":
                            response_buffer += event.data.delta
                    event_converter.console.rule()
                except Exception as e:
                    logger.error(f"Error during streaming: {e}", exc_info=True)
                return False

            if PromptSession is not None:
                command_help: dict[str, str] = {
                    "/help": "Show help",
                    "/clear": "Clear conversation and free context",
                    "/compact": "Keep a summary in context",
                    "/status": "Show current setup",
                    "/exit": "Quit",
                }

                command_display_overrides: dict[str, str] = {
                    "/exit": "/exit (quit)",
                    "/clear": "/clear (reset)",
                    "/compact": "/compact [instructions]",
                }

                class SlashCompleter(Completer):  # type: ignore[misc]
                    def get_completions(self, document, complete_event):  # type: ignore[override]
                        text = document.text_before_cursor
                        if not text or not text.startswith("/"):
                            return

                        # Show all commands when just "/" is typed
                        if text == "/":
                            entries = list(command_help.keys())
                        else:
                            # Filter commands that start with the typed text
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
                def _(event):
                    """Handle Ctrl+C gracefully."""
                    event.app.exit(exception=KeyboardInterrupt)

                @bindings.add("/")
                def _(event):
                    """Insert '/' and immediately open the completion menu."""
                    buf = event.app.current_buffer
                    buf.insert_text("/")
                    # Force completion menu to open for slash commands
                    buf.start_completion(select_first=True)

                try:
                    session = PromptSession(
                        history=history,
                        key_bindings=bindings,
                        enable_history_search=True,
                        mouse_support=False,  # Disable mouse to avoid terminal issues
                    )
                except Exception:
                    # Fall back to basic input mode if PromptSession fails
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
                            # Handle termios errors and similar issues - fall back to basic input
                            PromptSession = None
                            break

                        event_converter.console.rule()
                        should_exit = await handle_message(message)
                        if should_exit:
                            return
            else:
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
