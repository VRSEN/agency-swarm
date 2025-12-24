import asyncio
import importlib
import inspect
import io
import logging
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, VSplit, Window
from prompt_toolkit.layout.containers import ConditionalContainer
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame
from rich.markup import escape as rich_escape
from watchfiles import watch

from agency_swarm.agency.core import Agency
from agency_swarm.messages import MessageFilter
from agency_swarm.utils import is_reasoning_model
from agency_swarm.utils.usage_tracking import (
    UsageStats,
    calculate_usage_with_cost,
    extract_usage_from_run_result,
    format_usage_for_display,
)

from ..core.console_event_adapter import ConsoleEventAdapter
from .launcher import TerminalDemoLauncher

_MSVCRT = importlib.import_module("msvcrt") if sys.platform == "win32" else None
_SELECT = importlib.import_module("select") if sys.platform != "win32" else None
_TERMIOS = importlib.import_module("termios") if sys.platform != "win32" else None
_TTY = importlib.import_module("tty") if sys.platform != "win32" else None


class EscapeKeyWatcher:
    """Cross-platform ESC key detector that runs in background."""

    def __init__(self) -> None:
        self._escape_pressed = False
        self._stop = False
        self._thread: threading.Thread | None = None

    def check(self) -> bool:
        """Return True if ESC was pressed since last check."""
        result = self._escape_pressed
        self._escape_pressed = False
        return result

    def _poll_windows(self) -> None:
        """Windows key polling using msvcrt (Windows-only standard library)."""
        if _MSVCRT is None:
            return

        msvcrt_any = cast(Any, _MSVCRT)

        while not self._stop:
            try:
                if msvcrt_any.kbhit():
                    key = msvcrt_any.getch()
                    if key == b"\x1b":  # ESC
                        self._escape_pressed = True
                    elif key in (b"\x00", b"\xe0"):
                        msvcrt_any.getch()
                else:
                    time.sleep(0.05)
            except Exception:
                break

    def _poll_unix(self) -> None:
        """Unix key polling using select (Unix-only standard library modules)."""
        if None in (_SELECT, _TERMIOS, _TTY):
            return

        select_module = cast(ModuleType, _SELECT)
        termios_module = cast(ModuleType, _TERMIOS)
        tty_module = cast(ModuleType, _TTY)

        select_any = cast(Any, select_module)
        termios_any = cast(Any, termios_module)
        tty_any = cast(Any, tty_module)

        old_settings = None
        try:
            fd = sys.stdin.fileno()
            old_settings = termios_any.tcgetattr(fd)
            tty_any.setcbreak(fd)

            while not self._stop:
                if select_any.select([sys.stdin], [], [], 0.05)[0]:
                    key = sys.stdin.read(1)
                    if key == "\x1b":  # ESC
                        self._escape_pressed = True
        except Exception:
            pass
        finally:
            if old_settings is not None:
                try:
                    termios_any.tcsetattr(fd, termios_any.TCSADRAIN, old_settings)
                except Exception:
                    pass

    def start(self) -> None:
        """Start watching for ESC key in background thread.

        Gracefully degrades in test environments where stdin is mocked.
        """
        self._stop = False
        self._escape_pressed = False

        # Check if stdin is a real terminal (not mocked in tests)
        try:
            sys.stdin.fileno()
        except (io.UnsupportedOperation, AttributeError, OSError):
            # stdin is mocked/redirected - skip key watching
            return

        target = self._poll_windows if sys.platform == "win32" else self._poll_unix
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the watcher thread and wait for it to finish."""
        self._stop = True
        if self._thread is not None:
            self._thread.join(timeout=0.5)  # Wait up to 0.5s for thread to finish
            self._thread = None


# Environment variable to mark child process in reload mode
# Values: "0" = initial spawn, "1" = respawn after file change (auto-resume)
_RELOAD_CHILD_ENV = "_AGENCY_TERMINAL_RELOAD_CHILD"


def _get_caller_script_path() -> Path | None:
    """Extract the script path that called start_terminal() using inspect.

    Walks up the stack to find the first file outside the agency_swarm package.
    """
    frame = inspect.currentframe()
    try:
        caller_frame = frame
        while caller_frame is not None:
            caller_file = caller_frame.f_code.co_filename
            # Skip frames from the agency_swarm package
            if "agency_swarm" not in caller_file:
                return Path(caller_file).resolve()
            caller_frame = caller_frame.f_back
        return None
    finally:
        del frame


def _get_watch_directory(script_path: Path) -> Path:
    """Determine the directory to watch for file changes."""
    # Watch the directory containing the script (the agency folder)
    return script_path.parent


class TerminalReloader:
    """Watches for file changes and restarts the terminal demo subprocess."""

    def __init__(self, script_path: Path, watch_dir: Path) -> None:
        self._script_path = script_path
        self._watch_dir = watch_dir
        self._child_process: subprocess.Popen[bytes] | None = None
        self._stop_requested = False
        self._logger = logging.getLogger(__name__)

    def _spawn_child(self, is_restart: bool = False) -> subprocess.Popen[bytes]:
        """Spawn a child process running the terminal demo."""
        env = os.environ.copy()
        env[_RELOAD_CHILD_ENV] = "1" if is_restart else "0"

        # Platform-specific flags
        kwargs: dict[str, Any] = {
            "env": env,
            "stdin": sys.stdin,
            "stdout": sys.stdout,
            "stderr": sys.stderr,
        }

        if sys.platform == "win32":
            # Windows: create in new process group so CTRL_C doesn't propagate to parent
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        # Use the same Python interpreter
        return subprocess.Popen([sys.executable, str(self._script_path)], **kwargs)

    def _terminate_child(self) -> None:
        """Terminate the child process gracefully."""
        if self._child_process is None:
            return

        try:
            # Use terminate() on all platforms - it's clean and doesn't affect parent
            # On Windows: sends TerminateProcess
            # On Unix: sends SIGTERM
            self._child_process.terminate()

            # Wait for graceful shutdown
            try:
                self._child_process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._child_process.kill()
                self._child_process.wait()
        except Exception as e:
            self._logger.debug(f"Error terminating child: {e}")
        finally:
            self._child_process = None

    def run(self) -> None:
        """Run the reloader loop: watch files and restart child on changes."""
        print(f"\n🔄 Hot reload enabled. Watching: {self._watch_dir}")
        print("   Changes to .py and .md files will trigger a restart.\n")

        # File filter: only watch .py and .md files
        def should_watch(change_type: Any, path: str) -> bool:
            return path.endswith((".py", ".md"))

        is_restart = False  # First spawn is not a restart
        try:
            while not self._stop_requested:
                # Spawn child process
                self._child_process = self._spawn_child(is_restart=is_restart)
                is_restart = True  # Subsequent spawns are restarts

                # Watch for file changes while child is running
                try:
                    for changes in watch(
                        self._watch_dir,
                        watch_filter=should_watch,
                        stop_event=None,
                        yield_on_timeout=True,
                        rust_timeout=500,  # Check every 500ms
                    ):
                        # Check if child exited
                        if self._child_process.poll() is not None:
                            # Child exited normally (user quit)
                            return

                        if changes:
                            # File changes detected
                            changed_files = [str(Path(path).relative_to(self._watch_dir)) for _, path in changes]
                            print(f"\n🔄 Detected changes in: {', '.join(changed_files)}")
                            print("   Reloading...\n")
                            break
                except KeyboardInterrupt:
                    self._stop_requested = True
                    break

                # Restart: terminate old child and loop to spawn new one
                self._terminate_child()

        except KeyboardInterrupt:
            pass
        finally:
            self._terminate_child()


@dataclass
class DropdownItem:
    label: str
    description: str
    insertion_text: str
    append_space: bool = False


class DropdownMenu:
    def __init__(self, invalidate: Callable[[], None]) -> None:
        self._invalidate = invalidate
        self.visible = False
        self.items: list[DropdownItem] = []
        self.selected_index = 0
        self.max_label_width = 0

    def update_invalidator(self, invalidate: Callable[[], None]) -> None:
        self._invalidate = invalidate

    def set_items(self, items: list[DropdownItem]) -> None:
        if items:
            self.items = items
            self.max_label_width = max(len(item.label) for item in items)
            if self.selected_index >= len(items):
                self.selected_index = 0
            self.visible = True
        else:
            self.items = []
            self.max_label_width = 0
            self.selected_index = 0
            self.visible = False
        self._invalidate()

    def hide(self) -> None:
        if self.visible:
            self.visible = False
            self._invalidate()

    def move(self, offset: int) -> None:
        if not self.visible or not self.items:
            return
        self.selected_index = (self.selected_index + offset) % len(self.items)
        self._invalidate()

    def get_selected(self) -> DropdownItem | None:
        if not self.items:
            return None
        return self.items[self.selected_index]

    def render(self) -> AnyFormattedText:
        if not self.visible or not self.items:
            return []
        lines: list[tuple[str, str]] = []
        for idx, item in enumerate(self.items):
            style = "class:dropdown.selected" if idx == self.selected_index else "class:dropdown.item"
            pointer = "▸ " if idx == self.selected_index else "  "
            label = item.label.ljust(self.max_label_width)
            lines.append((style, f"{pointer}{label}  {item.description}\n"))
        return cast(AnyFormattedText, lines)


def start_terminal(
    agency_instance: Agency,
    show_reasoning: bool | None = None,
    reload: bool = True,
) -> None:
    """Run the terminal demo: input loop, slash commands, and streaming output.

    Args:
        agency_instance: The Agency instance to run.
        show_reasoning: Whether to show reasoning output. Auto-detected if None.
        reload: If True, watch for file changes and automatically restart on changes.
                Uses the same approach as uvicorn --reload.
    """
    logger = logging.getLogger(__name__)

    # Hot reload: if enabled and we're the parent, run the reloader loop
    if reload and not os.environ.get(_RELOAD_CHILD_ENV):
        script_path = _get_caller_script_path()
        if script_path is None:
            logger.warning("Could not determine script path for hot reload. Running without reload.")
        else:
            watch_dir = _get_watch_directory(script_path)
            reloader = TerminalReloader(script_path, watch_dir)
            reloader.run()
            return

    recipient_agents = [str(agent.name) for agent in agency_instance.entry_points]
    if not recipient_agents:
        raise ValueError("Cannot start terminal demo without entry points. Please specify at least one entry point.")

    if show_reasoning is None:
        show_reasoning = any(is_reasoning_model(agent.model) for agent in agency_instance.agents.values())

    # Auto-resume on hot reload only (not on initial boot)
    resumed_chat_id: str | None = None
    resumed_usage: UsageStats | None = None
    if os.environ.get(_RELOAD_CHILD_ENV) == "1":
        records = TerminalDemoLauncher.list_chat_records()
        if records:
            most_recent_id = records[0]["chat_id"]
            if TerminalDemoLauncher.load_chat(agency_instance, most_recent_id):
                resumed_chat_id = most_recent_id
                # Restore usage from saved metadata.
                metadata = TerminalDemoLauncher.load_chat_metadata(most_recent_id)
                if metadata and "usage" in metadata:
                    saved_usage = metadata["usage"]
                    resumed_usage = UsageStats(
                        request_count=saved_usage.get("request_count", 0),
                        cached_tokens=saved_usage.get("cached_tokens", 0),
                        input_tokens=saved_usage.get("input_tokens", 0),
                        output_tokens=saved_usage.get("output_tokens", 0),
                        total_tokens=saved_usage.get("total_tokens", 0),
                        total_cost=saved_usage.get("total_cost", 0.0),
                        reasoning_tokens=saved_usage.get("reasoning_tokens"),
                        audio_tokens=saved_usage.get("audio_tokens"),
                    )

    chat_id = resumed_chat_id if resumed_chat_id else TerminalDemoLauncher.start_new_chat(agency_instance)

    event_converter = ConsoleEventAdapter(show_reasoning=show_reasoning, agents=list(agency_instance.agents.keys()))
    event_converter.console.rule()
    try:
        cwd = os.getcwd()
        banner_name = getattr(agency_instance, "name", None) or "Agency Swarm"
        event_converter.console.print(f"[bold]* Welcome to {banner_name}![/bold]")
        event_converter.console.print("\n/help for help, /status for your current setup")
        event_converter.console.print("[dim]Press ESC during streaming to cancel[/dim]\n")
        event_converter.console.print(f"cwd: {cwd}\n")
        if resumed_chat_id:
            event_converter.console.print(f"[green]♻ Resumed conversation: {chat_id}[/green]\n")
        event_converter.console.rule()
    except Exception:
        pass

    current_default_recipient = agency_instance.entry_points[0].name

    # Track accumulated usage for the session (restore from saved if available).
    session_usage = resumed_usage if resumed_usage else UsageStats()

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
            ("/cost", "Show current usage and costs"),
            ("/exit (quit)", "Quit"),
        ]
        for cmd, desc in rows:
            event_converter.console.print(f"[cyan]{cmd}[/cyan]  {desc}")
        event_converter.console.rule()

    def _print_cost() -> None:
        """Display current accumulated usage and costs."""
        nonlocal session_usage
        if session_usage.total_tokens == 0:
            event_converter.console.print("[dim]No usage tracked yet.[/dim]")
        else:
            event_converter.console.print("[bold]Session Usage:[/bold]")
            event_converter.console.print(format_usage_for_display(session_usage))
        event_converter.console.rule()

    def _print_exit_info() -> None:
        """Print usage and chat_id on exit."""
        nonlocal chat_id, session_usage
        event_converter.console.print(f"\n[bold]Chat ID:[/bold] {chat_id}")
        if session_usage.total_tokens > 0:
            event_converter.console.print("\n[bold]Session Usage:[/bold]")
            event_converter.console.print(format_usage_for_display(session_usage))
        event_converter.console.print("\n[dim]To resume this conversation, use: /resume[/dim]")

    def _start_new_chat() -> None:
        """Start a chat session with a fresh chat id."""
        nonlocal chat_id, session_usage
        chat_id = TerminalDemoLauncher.start_new_chat(agency_instance)
        session_usage = UsageStats()  # Reset usage for new chat
        event_converter.console.print("Started a new chat session.")
        event_converter.console.rule()
        event_converter.handoff_agent = None

    def _resume_chat() -> None:
        """Load a previously saved chat into context."""
        nonlocal chat_id, session_usage
        chosen = TerminalDemoLauncher.resume_interactive(
            agency_instance, input_func=input, print_func=event_converter.console.print
        )
        if chosen:
            chat_id = chosen
            # Restore usage from saved metadata.
            metadata = TerminalDemoLauncher.load_chat_metadata(chat_id)
            if metadata and "usage" in metadata:
                saved_usage = metadata["usage"]
                session_usage = UsageStats(
                    request_count=saved_usage.get("request_count", 0),
                    cached_tokens=saved_usage.get("cached_tokens", 0),
                    input_tokens=saved_usage.get("input_tokens", 0),
                    output_tokens=saved_usage.get("output_tokens", 0),
                    total_tokens=saved_usage.get("total_tokens", 0),
                    total_cost=saved_usage.get("total_cost", 0.0),
                    reasoning_tokens=saved_usage.get("reasoning_tokens"),
                    audio_tokens=saved_usage.get("audio_tokens"),
                )
            else:
                session_usage = UsageStats()  # Reset if no saved usage.
            event_converter.console.print(f"Resumed chat: {chat_id}")
        event_converter.console.rule()
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
        nonlocal chat_id, current_default_recipient, session_usage
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
            if cmd == "cost":
                _print_cost()
                return False
            if cmd == "compact":
                await _compact_chat(args)
                return False
            if cmd == "exit":
                _print_exit_info()
                return True

        recipient_agent = None
        agent_mention_pattern = r"(?:^|\s|,)@(\w+)(?:\s|,|$)"
        agent_match = re.search(agent_mention_pattern, message)

        if message.startswith("@"):
            mentioned_agent = agent_match.group(1) if agent_match is not None else None
            sorted_agents = sorted(recipient_agents, key=len, reverse=True)
            lowered_message = message.lower()
            for agent in sorted_agents:
                agent_token = f"@{agent.lower()}"
                if not lowered_message.startswith(agent_token):
                    continue

                boundary_index = len(agent_token)
                if len(lowered_message) > boundary_index:
                    next_char = lowered_message[boundary_index]
                    if next_char.isalnum() or next_char == "_":
                        continue

                recipient_agent = agent
                message = message[boundary_index:].lstrip()
                break
            if recipient_agent is None:
                logger.error(f"Recipient agent {mentioned_agent or 'Unknown'} not found.", exc_info=True)
                return False

        if recipient_agent is not None and not message:
            event_converter.handoff_agent = recipient_agent
            event_converter.console.print(f"[cyan]Switched to {recipient_agent}[/cyan]")
            event_converter.console.rule()
            return False

        if recipient_agent is not None and recipient_agent != event_converter.handoff_agent:
            event_converter.handoff_agent = None

        escape_watcher = EscapeKeyWatcher()
        try:
            recipient_agent_str: str = (
                recipient_agent
                if recipient_agent is not None
                else event_converter.handoff_agent
                if event_converter.handoff_agent is not None
                else current_default_recipient
            )
            stream = agency_instance.get_response_stream(
                message=message, recipient_agent=recipient_agent_str, chat_id=chat_id
            )
            escape_watcher.start()

            cancelled = False
            async for event in stream:
                # Check for ESC key press
                if escape_watcher.check():
                    event_converter.console.print("\n[yellow]⏹ Cancelling stream...[/yellow]")
                    stream.cancel(mode="immediate")
                    cancelled = True
                    break

                event_converter.openai_to_message_output(event, recipient_agent_str)

            # Extract and accumulate usage from the stream result
            final_result = stream.final_result if stream else None
            if final_result:
                run_usage = extract_usage_from_run_result(final_result)
                if run_usage:
                    # Calculate cost - model_name is auto-extracted from run_result._main_agent_model
                    run_usage = calculate_usage_with_cost(run_usage, run_result=final_result)
                    session_usage = session_usage + run_usage

            # If cancelled, clean up display and filter orphaned/duplicate messages
            if cancelled:
                # Clean up any live displays and reset buffers
                event_converter._cleanup_live_display()

                # Filter out duplicates and orphaned messages
                all_messages = agency_instance.thread_manager.get_all_messages()
                filtered = MessageFilter.remove_duplicates(all_messages)
                filtered = MessageFilter.filter_messages(filtered)
                filtered = MessageFilter.remove_orphaned_messages(filtered)
                agency_instance.thread_manager.replace_messages(filtered)

            event_converter.console.rule()
            TerminalDemoLauncher.save_current_chat(agency_instance, chat_id, usage=session_usage.to_dict())
        except Exception as e:
            logger.error(f"Error during streaming: {e}", exc_info=True)
        finally:
            escape_watcher.stop()
        return False

    async def main_loop():
        nonlocal current_default_recipient

        command_help: dict[str, str] = {
            "/help": "Show help",
            "/new": "Start a new chat",
            "/compact": "Keep a summary in context",
            "/resume": "Resume a conversation",
            "/status": "Show current setup",
            "/cost": "Show usage and costs",
            "/exit": "Quit",
        }

        command_display_overrides: dict[str, str] = {
            "/exit": "/exit (quit)",
            "/compact": "/compact [instructions]",
        }

        dropdown_style = Style.from_dict(
            {
                "dropdown.window": "",
                "dropdown.item": "",
                "dropdown.selected": "reverse",
                "dropdown.border": "",
            }
        )

        active_recipient = current_default_recipient

        history = InMemoryHistory()
        bindings = KeyBindings()

        @bindings.add("c-c")
        def _(event) -> None:
            event.app.exit(exception=KeyboardInterrupt)

        buffer = Buffer(history=history)
        input_control = BufferControl(buffer=buffer, focusable=True)
        input_window = Window(content=input_control, always_hide_cursor=False)

        current_prompt = ""

        prompt_label_control = FormattedTextControl(lambda: current_prompt, focusable=False)
        prompt_label_window = Window(
            content=prompt_label_control,
            height=1,
            always_hide_cursor=True,
            dont_extend_width=True,
        )

        dropdown_menu = DropdownMenu(lambda: None)

        dropdown_container = ConditionalContainer(
            content=Frame(
                body=Window(
                    content=FormattedTextControl(dropdown_menu.render),
                    style="class:dropdown.window",
                    always_hide_cursor=True,
                ),
                style="class:dropdown.border",
            ),
            filter=Condition(lambda: dropdown_menu.visible),
        )

        root_container = HSplit([VSplit([prompt_label_window, input_window]), dropdown_container])

        application = Application(
            layout=Layout(root_container, focused_element=input_window),
            key_bindings=bindings,
            mouse_support=False,
            style=dropdown_style,
            full_screen=False,
            erase_when_done=True,
        )

        dropdown_menu.update_invalidator(application.invalidate)
        dropdown_visible = Condition(lambda: dropdown_menu.visible)

        suspend_refresh = False

        def _refresh_dropdown(_: object | None = None) -> None:
            nonlocal suspend_refresh
            if suspend_refresh:
                suspend_refresh = False
                return
            text = buffer.text
            if not text:
                dropdown_menu.hide()
                return
            if text.startswith("/"):
                prefix = text[1:].lower()
                items: list[DropdownItem] = []
                for cmd, description in command_help.items():
                    if prefix and not cmd[1:].startswith(prefix):
                        continue
                    display_label = command_display_overrides.get(cmd, cmd)
                    items.append(DropdownItem(label=display_label, description=description, insertion_text=cmd))
                dropdown_menu.set_items(items)
            elif text.startswith("@"):
                prefix = text[1:].lower()
                items = []
                for agent in recipient_agents:
                    if prefix and not agent.lower().startswith(prefix):
                        continue
                    description = "Currently selected" if agent == active_recipient else "Select this agent"
                    items.append(
                        DropdownItem(
                            label=f"@{agent}", description=description, insertion_text=f"@{agent}", append_space=True
                        )
                    )
                dropdown_menu.set_items(items)
            else:
                dropdown_menu.hide()

        buffer.on_text_changed += _refresh_dropdown

        def _insert_trigger(text: str) -> None:
            buffer.insert_text(text)
            _refresh_dropdown()

        @bindings.add("/")
        def _(event) -> None:
            _insert_trigger("/")

        @bindings.add("@")
        def _(event) -> None:
            _insert_trigger("@")

        @bindings.add("down", filter=dropdown_visible)
        def _(event) -> None:
            dropdown_menu.move(1)

        @bindings.add("up", filter=dropdown_visible)
        def _(event) -> None:
            dropdown_menu.move(-1)

        def _apply_selection() -> None:
            nonlocal suspend_refresh
            selection = dropdown_menu.get_selected()
            if selection is None:
                dropdown_menu.hide()
                return
            text = selection.insertion_text + (" " if selection.append_space else "")
            buffer.document = Document(text, len(text))
            dropdown_menu.hide()
            suspend_refresh = True

        @bindings.add("tab", filter=dropdown_visible, eager=True)
        def _(event) -> None:
            _apply_selection()

        @bindings.add("escape", filter=dropdown_visible, eager=True)
        def _(event) -> None:
            dropdown_menu.hide()

        @bindings.add("enter", eager=True)
        def _(event) -> None:
            nonlocal suspend_refresh
            if dropdown_menu.visible:
                _apply_selection()
                return
            result_text = buffer.text
            dropdown_menu.hide()
            suspend_refresh = True
            buffer.reset(Document(""))
            event.app.exit(result=result_text)

        while True:
            active_recipient = (
                event_converter.handoff_agent
                if event_converter.handoff_agent is not None
                else current_default_recipient
            )
            current_prompt = f"👤 USER -> 🤖 {active_recipient}: "
            dropdown_menu.hide()
            suspend_refresh = False
            application.invalidate()

            try:
                message = await application.run_async()
            except (KeyboardInterrupt, EOFError):
                _print_exit_info()
                return

            if message is None:
                return

            message_text = cast(str, message)
            if message_text.strip():
                history.append_string(message_text)

            current_prompt = ""
            application.invalidate()

            if message_text:
                event_converter.console.print(f"👤 USER -> 🤖 {active_recipient}: {rich_escape(message_text)}")

            event_converter.console.rule()
            should_exit = await handle_message(message_text)
            if should_exit:
                return

    try:
        asyncio.run(main_loop())
    except (KeyboardInterrupt, EOFError):
        # Exit info is printed inside main_loop before returning
        print("\n\nExiting terminal demo...")
