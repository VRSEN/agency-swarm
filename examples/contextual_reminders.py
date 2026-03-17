"""
Contextual Reminder Example

This example shows how to:
- store reminder state in agency context
- prepend a reminder system message before each user turn
- trigger a stronger reminder every 15 tool calls

Run:
    uv run python examples/contextual_reminders.py

If OPENAI_API_KEY is not set, the script runs a dry preview that prints the
structured input items instead of calling the API.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import Agency, Agent, MasterContext, ModelSettings, RunContextWrapper, function_tool  # noqa: E402

logging.basicConfig(level=logging.WARNING)
logging.getLogger("agency_swarm").setLevel(logging.WARNING)


def _increment_tool_counter(user_context: dict[str, Any], amount: int = 1) -> int:
    tool_calls = int(user_context.get("tool_calls_since_reminder", 0)) + amount
    user_context["tool_calls_since_reminder"] = tool_calls
    return tool_calls


def _format_follow_up(user_context: dict[str, Any]) -> str:
    follow_up = user_context.get("follow_up")
    if not isinstance(follow_up, dict):
        return "None recorded yet."

    owner = follow_up.get("owner", "unknown owner")
    promise = follow_up.get("promise", "unknown task")
    due = follow_up.get("due", "no due date")
    status = follow_up.get("status", "open")
    return f"{promise} (owner: {owner}, due: {due}, status: {status})"


def _store_follow_up(user_context: dict[str, Any], owner: str, promise: str, due: str) -> str:
    _increment_tool_counter(user_context)
    user_context["follow_up"] = {
        "owner": owner,
        "promise": promise,
        "due": due,
        "status": "open",
    }
    return f"Saved follow-up: {promise} (owner: {owner}, due: {due})."


def _complete_follow_up(user_context: dict[str, Any]) -> str:
    _increment_tool_counter(user_context)
    follow_up = user_context.get("follow_up")
    if not isinstance(follow_up, dict):
        return "No follow-up is stored yet."

    follow_up["status"] = "done"
    return f"Marked follow-up as done: {follow_up['promise']}."


@function_tool
async def save_follow_up(
    ctx: RunContextWrapper[MasterContext],
    owner: str,
    promise: str,
    due: str,
) -> str:
    """Store a follow-up item in agency context."""
    return _store_follow_up(ctx.context.user_context, owner, promise, due)


@function_tool
async def inspect_follow_up(ctx: RunContextWrapper[MasterContext]) -> str:
    """Inspect the reminder state currently stored in agency context."""
    _increment_tool_counter(ctx.context.user_context)
    return f"Current follow-up: {_format_follow_up(ctx.context.user_context)}"


@function_tool
async def complete_follow_up(ctx: RunContextWrapper[MasterContext]) -> str:
    """Mark the stored follow-up as complete."""
    return _complete_follow_up(ctx.context.user_context)


def build_reminder_message(user_context: dict[str, Any]) -> str:
    """Build the system reminder injected before each user turn."""
    base_reminder = str(
        user_context.get(
            "base_turn_reminder",
            "Before answering, restate the next follow-up and keep the reply actionable.",
        )
    )
    lines = [
        base_reminder,
        f"Stored follow-up: {_format_follow_up(user_context)}",
    ]

    checkpoint_interval = int(user_context.get("tool_call_reminder_interval", 15))
    tool_calls = int(user_context.get("tool_calls_since_reminder", 0))
    if checkpoint_interval > 0 and tool_calls >= checkpoint_interval:
        lines.append(
            f"Checkpoint reminder: {tool_calls} tool calls have happened since the last checkpoint. "
            "Summarize progress before using more tools."
        )
        user_context["tool_calls_since_reminder"] = 0

    return "\n".join(lines)


def build_turn_input(user_message: str, user_context: dict[str, Any]) -> list[dict[str, str]]:
    """Prepend a reminder system message before the current user turn."""
    return [
        {"role": "system", "content": build_reminder_message(user_context)},
        {"role": "user", "content": user_message},
    ]


def create_demo_agency() -> Agency:
    reminder_agent = Agent(
        name="ReminderAgent",
        instructions=(
            "You help with customer follow-ups. "
            "When a user asks to save, inspect, or complete a follow-up, always use the matching tool first. "
            "Then answer with a concise update that reflects the reminder system message."
        ),
        tools=[save_follow_up, inspect_follow_up, complete_follow_up],
        model_settings=ModelSettings(temperature=0.0),
    )

    return Agency(
        reminder_agent,
        user_context={
            "base_turn_reminder": "Before answering, mention the next follow-up and keep the response actionable.",
            "tool_call_reminder_interval": 15,
            "tool_calls_since_reminder": 0,
        },
    )


def _print_turn_preview(title: str, user_message: str, agency: Agency) -> None:
    print(f"\n{title}")
    print(json.dumps(build_turn_input(user_message, agency.user_context), indent=2))


def run_dry_preview() -> None:
    """Preview the reminder-enriched input items without calling the API."""
    agency = create_demo_agency()

    print("Contextual Reminder Demo (dry preview)")
    print("=" * 40)
    print("OPENAI_API_KEY is not set, so this run prints the structured input items only.")

    _print_turn_preview(
        "Turn 1: before any tool calls",
        "Save a follow-up for Acme: send the renewal deck by Friday. Ava owns it.",
        agency,
    )

    print("\nSimulating one tool call by updating agency context...")
    print(_store_follow_up(agency.user_context, owner="Ava", promise="Send the renewal deck", due="Friday"))

    _print_turn_preview(
        "Turn 2: reminder after context changes",
        "What follow-up is still open?",
        agency,
    )

    print("\nSimulating the optional 15-tool-call checkpoint...")
    agency.user_context["tool_calls_since_reminder"] = 15
    _print_turn_preview(
        "Turn 3: checkpoint reminder",
        "Draft a short customer update for the follow-up.",
        agency,
    )


async def run_live_demo() -> None:
    """Run the reminder pattern against a live model."""
    agency = create_demo_agency()

    print("Contextual Reminder Demo")
    print("=" * 30)

    turns = [
        "Save a follow-up for Acme: send the renewal deck by Friday. Ava owns it.",
        "What follow-up is still open?",
        "Draft a short customer update for the follow-up.",
    ]

    for index, user_message in enumerate(turns, start=1):
        if index == 3:
            agency.user_context["tool_calls_since_reminder"] = 15

        print(f"\nTurn {index}")
        response = await agency.get_response(build_turn_input(user_message, agency.user_context))
        print(response.final_output)


if __name__ == "__main__":
    if os.getenv("OPENAI_API_KEY"):
        asyncio.run(run_live_demo())
    else:
        run_dry_preview()
