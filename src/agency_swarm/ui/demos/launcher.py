import asyncio
import uuid
from typing import Any

from prompt_toolkit.shortcuts import radiolist_dialog

from agency_swarm import Agency

from .compact import (
    compact_thread as _build_compact_summary,
    get_compact_prompt as _get_compact_prompt,
    set_compact_prompt as _set_compact_prompt,
)
from .persistence import (
    format_relative as _format_relative,
    index_file_path as _index_file_path,
    list_chat_records as _list_chat_records,
    load_chat as _load_chat,
    save_current_chat as _save_current_chat,
    set_chats_dir as _set_chats_dir,
)

"""Terminal demo launcher.

This module focuses on terminal interaction only. Copilot demo is in _copilot.py.
"""


class TerminalDemoLauncher:
    # Tracks the currently active chat id
    CURRENT_CHAT_ID: str | None = None
    # Configurable prompt used by /compact. Override via TerminalDemoLauncher.set_compact_prompt(...)
    COMPACT_PROMPT: str = _get_compact_prompt()

    @staticmethod
    def set_compact_prompt(prompt: str) -> None:
        prompt_str = str(prompt)
        _set_compact_prompt(prompt_str)
        TerminalDemoLauncher.COMPACT_PROMPT = prompt_str

    @staticmethod
    def set_chats_dir(path: str) -> None:
        """Set directory where chats are stored as JSON files."""
        _set_chats_dir(str(path))

    @staticmethod
    def generate_chat_id() -> str:
        """Create a unique chat id for new sessions."""
        return f"run_demo_chat_{uuid.uuid4()}"

    @staticmethod
    def get_current_chat_id() -> str | None:
        """Return the most recently active chat id, if any."""
        return TerminalDemoLauncher.CURRENT_CHAT_ID

    @staticmethod
    def set_current_chat_id(chat_id: str | None) -> None:
        """Set the active chat id for the launcher."""
        TerminalDemoLauncher.CURRENT_CHAT_ID = chat_id

    @staticmethod
    def _index_file_path() -> str:
        return _index_file_path()

    @staticmethod
    def save_current_chat(agency_instance: Agency, chat_id: str) -> None:
        """Persist current flat messages to disk for the given chat_id."""
        _save_current_chat(agency_instance, chat_id)

    @staticmethod
    def load_chat(agency_instance: Agency, chat_id: str) -> bool:
        """Load messages for chat_id into agency thread manager. Returns True if loaded."""
        loaded = _load_chat(agency_instance, chat_id)
        if not loaded:
            return False
        TerminalDemoLauncher.set_current_chat_id(chat_id)
        return True

    @staticmethod
    def start_new_chat(agency_instance: Agency, chat_id: str | None = None) -> str:
        """Switch the launcher and agency to a fresh chat id with an empty thread."""
        new_chat_id = chat_id or TerminalDemoLauncher.generate_chat_id()
        TerminalDemoLauncher.set_current_chat_id(new_chat_id)

        # Reset the thread store
        agency_instance.thread_manager.replace_messages([])

        return new_chat_id

    @staticmethod
    def _format_relative(ts_iso: str | None) -> str:
        return _format_relative(ts_iso)

    @staticmethod
    def list_chat_records() -> list[dict[str, Any]]:
        return _list_chat_records()

    @staticmethod
    def resume_interactive(
        agency_instance: Agency,
        *,
        input_func: Any | None = None,
        print_func: Any | None = None,
    ) -> str | None:
        """Render an interactive resume selector and load chosen chat.

        Returns the selected chat_id if loaded; otherwise None.
        """
        records = TerminalDemoLauncher.list_chat_records()
        if not records:
            if print_func:
                print_func("No saved chats.")
            else:
                print("No saved chats.")
            return None

        # Try fancy menu with arrow keys first (only if no event loop is running)
        loop_running = False
        try:
            asyncio.get_running_loop()
            loop_running = True
        except RuntimeError:
            loop_running = False

        if not loop_running:
            choices = []
            for rec in records:
                mod = TerminalDemoLauncher._format_relative(rec.get("modified_at"))
                created = TerminalDemoLauncher._format_relative(rec.get("created_at"))
                msgs = rec.get("msgs") or 0
                branch = (rec.get("branch") or "")[:20]
                summary = (rec.get("summary") or "").strip()[:40]

                display = f"{mod:<12} {created:<12} {msgs:>3} {branch:<20} {summary}"
                choices.append((rec["chat_id"], display))

            result = radiolist_dialog(
                title="Resume Chat",
                text="Use arrow keys to select a chat:",
                values=choices,
            ).run()

            if result:
                if TerminalDemoLauncher.load_chat(agency_instance, result):
                    return result

        # Fallback: simple number selection
        input_fn = input_func or input
        printer = print_func or print

        printer("      Modified     Created        Msgs Git Branch           Summary")
        for idx, rec in enumerate(records, 1):
            mod = TerminalDemoLauncher._format_relative(rec.get("modified_at"))
            created = TerminalDemoLauncher._format_relative(rec.get("created_at"))
            msgs = str(rec.get("msgs") or 0).rjust(3)
            branch = (rec.get("branch") or "")[0:22].ljust(22)
            summary = (rec.get("summary") or "").strip()
            printer(f"{str(idx) + '.':>3}  {mod:<12}  {created:<12}  {msgs} {branch} {summary}")

        try:
            selection = str(input_fn("Select a chat number to resume (or press Enter to cancel): ")).strip()
        except Exception:
            selection = ""
        if not selection:
            return None
        try:
            sel_idx = int(selection)
        except Exception:
            printer("Invalid selection.")
            return None
        if sel_idx < 1 or sel_idx > len(records):
            printer("Selection out of range.")
            return None

        target_id = records[sel_idx - 1]["chat_id"]
        if TerminalDemoLauncher.load_chat(agency_instance, target_id):
            return target_id
        printer(f"Chat not found: {target_id}")
        return None

    @staticmethod
    async def compact_thread(agency_instance: Agency, args: list[str]) -> str:
        prev = TerminalDemoLauncher.get_current_chat_id()
        try:
            summary_message = await _build_compact_summary(agency_instance, args)
            chat_id = TerminalDemoLauncher.start_new_chat(agency_instance)
            agency_instance.thread_manager.replace_messages([summary_message])
            return chat_id
        except Exception as e:
            TerminalDemoLauncher.set_current_chat_id(prev)
            raise RuntimeError(f"/compact failed: {e}") from e

    @staticmethod
    def start(agency_instance: Agency, show_reasoning: bool = False) -> None:
        from .terminal import start_terminal  # defer import to keep file light

        start_terminal(agency_instance, show_reasoning=show_reasoning)
