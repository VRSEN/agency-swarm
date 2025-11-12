import asyncio
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
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

from agency_swarm.agency.core import Agency
from agency_swarm.utils import is_reasoning_model

from ..core.console_event_adapter import ConsoleEventAdapter
from .launcher import TerminalDemoLauncher


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
            # Preserve selection when possible
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
) -> None:
    """Run the terminal demo: input loop, slash commands, and streaming output."""
    logger = logging.getLogger(__name__)

    recipient_agents = [str(agent.name) for agent in agency_instance.entry_points]
    if not recipient_agents:
        raise ValueError("Cannot start terminal demo without entry points. Please specify at least one entry point.")

    # Auto-detect show_reasoning if not explicitly provided
    if show_reasoning is None:
        # Check if any agent in the agency uses a reasoning model
        show_reasoning = any(is_reasoning_model(agent.model) for agent in agency_instance.agents.values())

    chat_id = TerminalDemoLauncher.start_new_chat(agency_instance)

    event_converter = ConsoleEventAdapter(show_reasoning=show_reasoning, agents=list(agency_instance.agents.keys()))
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
        agent_mention_pattern = r"(?:^|\s|,)@(\w+)(?:\s|,|$)"
        agent_match = re.search(agent_mention_pattern, message)

        if message.startswith("@"):
            mentioned_agent = agent_match.group(1) if agent_match is not None else None
            # Sort from longest to shortest to avoid matching partial names
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

        # If only an agent mention with no message, switch to that agent without sending
        if recipient_agent is not None and not message:
            event_converter.handoff_agent = recipient_agent
            event_converter.console.print(f"[cyan]Switched to {recipient_agent}[/cyan]")
            event_converter.console.rule()
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
                message=message, recipient_agent=recipient_agent_str, chat_id=chat_id
            ):
                event_converter.openai_to_message_output(event, recipient_agent_str)
            event_converter.console.rule()
            TerminalDemoLauncher.save_current_chat(agency_instance, chat_id)
        except Exception as e:
            logger.error(f"Error during streaming: {e}", exc_info=True)
        return False

    async def main_loop():
        # prompt_toolkit is a mandatory dependency; imported at module load
        nonlocal current_default_recipient

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
            # Determine the active recipient for display
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
                return

            if message is None:
                return

            message_text = cast(str, message)
            if message_text.strip():
                history.append_string(message_text)

            current_prompt = ""
            application.invalidate()

            if message_text:
                event_converter.console.print(f"👤 USER -> 🤖 {active_recipient}: {message_text}")

            event_converter.console.rule()
            should_exit = await handle_message(message_text)
            if should_exit:
                return

    try:
        asyncio.run(main_loop())
    except (KeyboardInterrupt, EOFError):
        print("\n\nExiting terminal demo...")
