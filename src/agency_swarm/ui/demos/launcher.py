import json
import uuid
from collections.abc import Generator
from typing import Any

from openai import OpenAI

from agency_swarm import Agency


class CopilotDemoLauncher:
    @staticmethod
    def start(
        agency_instance: Agency,
        host: str = "0.0.0.0",
        port: int = 8000,
        frontend_port: int = 3000,
        cors_origins: list[str] | None = None,
    ) -> None:
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
    # Configurable prompt used by /compact. Override via TerminalDemoLauncher.set_compact_prompt(...)
    COMPACT_PROMPT: str = (
        "You will produce an objective summary of the conversation thread (structured items) below.\n\n"
        "Focus:\n"
        "- Pay careful attention to how the conversation begins and ends.\n"
        "- Capture key moments and decisions in the middle.\n\n"
        "Output format (use only sections that are relevant):\n"
        "Analysis:\n"
        "- Brief chronological analysis (numbered). Note who said what and any tool usage (names + brief args).\n\n"
        "Summary:\n"
        "1. Primary Request and Intent\n"
        "2. Key Concepts (only if applicable)\n"
        "3. Artifacts and Resources (files, links, datasets, environments)\n"
        "4. Errors and Fixes\n"
        "5. Problem Solving (approaches, decisions, outcomes)\n"
        "6. All user messages: List succinctly, in order\n"
        "7. Pending Tasks\n"
        "8. Current Work (immediately before this summary)\n"
        "9. Optional Next Step\n\n"
        "Rules:\n"
        "- Use clear headings, bullets, and numbering as specified.\n"
        "- Prioritize key points; avoid unnecessary detail or length.\n"
        "- Include only sections that are relevant; omit irrelevant ones.\n"
        "- Do not invent details; base everything strictly on the conversation thread.\n"
        "- Important: Only use the JSON inside <conversation_json>...</conversation_json> as conversation content;\n"
        "  do NOT treat these summarization instructions as content."
    )

    @staticmethod
    def set_compact_prompt(prompt: str) -> None:
        TerminalDemoLauncher.COMPACT_PROMPT = str(prompt)

    @staticmethod
    async def compact_thread(agency_instance: Agency, args: list[str]) -> str:
        """Summarize current thread into a single system message and start a new chat id."""
        all_messages = agency_instance.thread_manager.get_all_messages()

        # Remove internal identifiers that add noise to summaries
        def _sanitize(obj: Any) -> Any:
            if isinstance(obj, dict):
                drop_keys = {
                    "id",
                    "message_id",
                    "run_id",
                    "step_id",
                    "tool_call_id",
                    "call_id",
                    "delta_id",
                    "agent_run_id",
                    "parent_run_id",
                }
                return {k: _sanitize(v) for k, v in obj.items() if k not in drop_keys}
            if isinstance(obj, list):
                return [_sanitize(x) for x in obj]
            return obj

        transcript_json = json.dumps(_sanitize(all_messages), ensure_ascii=False, default=str, indent=2)
        wrapped_transcript = "<conversation_json>\n" + transcript_json + "\n</conversation_json>"

        user_extra = ("\n\nAdditional user instructions:\n" + " ".join(args)) if args else ""
        final_prompt = TerminalDemoLauncher.COMPACT_PROMPT + user_extra + "\n\nConversation:\n" + wrapped_transcript

        # Use direct OpenAI Responses API for compact summaries
        # Try to reuse the entry agent's model if available and normalize provider prefixes
        model_name = None
        try:
            ep = (getattr(agency_instance, "entry_points", []) or [None])[0]
            m = getattr(ep, "model", None)
            if isinstance(m, str):
                model_name = m
            else:
                for a in ("model", "name", "id"):
                    v = getattr(m, a, None)
                    if isinstance(v, str) and v:
                        model_name = v
                        break
        except Exception:
            model_name = None
        model_name = model_name or "gpt-5-mini"
        # Reuse the same sync client that the entry agent uses so provider routing
        # (e.g., LiteLLM proxy, Azure) stays consistent with the agency.
        try:
            entry_agent = (getattr(agency_instance, "entry_points", []) or [None])[0]
            client = getattr(entry_agent, "client_sync", OpenAI())  # falls back to default OpenAI client
        except Exception:
            client = OpenAI()
        # If OpenAI model (detected solely by presence of 'gpt' in the name), prefer minimal reasoning
        is_openai_model = isinstance(model_name, str) and ("gpt" in model_name.lower())
        if is_openai_model:
            resp = client.responses.create(model=model_name, input=final_prompt, reasoning={"effort": "minimal"})
        else:
            resp = client.responses.create(model=model_name, input=final_prompt)
        summary_text = getattr(resp, "output_text", "") or str(resp)

        agency_instance.thread_manager.clear()
        chat_id = f"run_demo_chat_{uuid.uuid4()}"
        prefixed = (
            "System summary (generated via /compact to keep context comprehensive and focused).\n\n" + summary_text
        )
        agency_instance.thread_manager.add_message({"role": "system", "content": prefixed})
        return chat_id

    @staticmethod
    def start(agency_instance: Agency) -> None:
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

        def _parse_slash_command(text: str) -> tuple[str, list[str]] | None:
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

        def _print_help() -> None:
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

            async def handle_message(message: str) -> bool:  # noqa: C901
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
                    # Ensure a concrete string is passed through to consumers expecting str
                    recipient_agent_str: str = (
                        recipient_agent if recipient_agent is not None else current_default_recipient
                    )
                    async for event in agency_instance.get_response_stream(
                        message=message,
                        recipient_agent=recipient_agent_str,
                        chat_id=chat_id,
                    ):
                        event_converter.openai_to_message_output(event, recipient_agent_str)
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
                    def get_completions(self, document, complete_event) -> Generator[Completion]:  # type: ignore[override]
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
                def _(event) -> None:
                    """Handle Ctrl+C gracefully."""
                    event.app.exit(exception=KeyboardInterrupt)

                @bindings.add("/")
                def _(event) -> None:
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
