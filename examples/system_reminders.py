"""
System Reminders Example

This example shows how to:
- store reminder data in agency context
- configure first-class Agent system reminders
- inject a reminder after each new user message
- inject a stronger reminder after every 15 tool calls

Run:
    uv run python examples/system_reminders.py

If OPENAI_API_KEY is not set, the script runs a dry preview that prints the
structured input items that the configured reminders would inject.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any

# Path setup for standalone examples
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from agency_swarm import (  # noqa: E402
    AfterEveryUserMessage,
    Agency,
    Agent,
    EveryNToolCalls,
    MasterContext,
    ModelSettings,
    RunContextWrapper,
    function_tool,
)

logging.basicConfig(level=logging.WARNING)
logging.getLogger("agency_swarm").setLevel(logging.WARNING)


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
    user_context["follow_up"] = {
        "owner": owner,
        "promise": promise,
        "due": due,
        "status": "open",
    }
    return f"Saved follow-up: {promise} (owner: {owner}, due: {due})."


def _complete_follow_up(user_context: dict[str, Any]) -> str:
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
    return f"Current follow-up: {_format_follow_up(ctx.context.user_context)}"


@function_tool
async def complete_follow_up(ctx: RunContextWrapper[MasterContext]) -> str:
    """Mark the stored follow-up as complete."""
    return _complete_follow_up(ctx.context.user_context)


def build_follow_up_reminder(ctx: RunContextWrapper[MasterContext], _agent: Agent) -> str:
    """Render the per-user-message reminder from agency context."""
    user_context = ctx.context.user_context
    base_reminder = str(
        user_context.get(
            "base_turn_reminder",
            "Before answering, restate the next follow-up and keep the reply actionable.",
        )
    )
    return "\n".join(
        [
            base_reminder,
            f"Stored follow-up: {_format_follow_up(user_context)}",
        ]
    )


def build_checkpoint_reminder(ctx: RunContextWrapper[MasterContext], _agent: Agent) -> str:
    """Render the tool-call checkpoint reminder from agency context."""
    return "\n".join(
        [
            "Checkpoint reminder: 15 tool calls have happened since the last checkpoint.",
            f"Stored follow-up: {_format_follow_up(ctx.context.user_context)}",
            "Summarize progress before using more tools.",
        ]
    )


def preview_turn_input(user_message: str, agency: Agency, include_checkpoint: bool = False) -> list[dict[str, str]]:
    """Preview the reminder-enriched input items for this example."""
    agent = agency.agents["ReminderAgent"]
    preview_context = RunContextWrapper(
        MasterContext(
            thread_manager=agency.thread_manager,
            agents=agency.agents,
            user_context=agency.user_context,
            current_agent_name=agent.name,
        )
    )
    preview_items: list[dict[str, str]] = []
    for reminder in agent.system_reminders:
        if isinstance(reminder, AfterEveryUserMessage):
            preview_items.append({"role": "system", "content": reminder.render(preview_context, agent)})
        if include_checkpoint and isinstance(reminder, EveryNToolCalls):
            preview_items.append({"role": "system", "content": reminder.render(preview_context, agent)})
    preview_items.append({"role": "user", "content": user_message})
    return preview_items


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
        system_reminders=[
            AfterEveryUserMessage(build_follow_up_reminder),
            EveryNToolCalls(15, build_checkpoint_reminder),
        ],
    )

    return Agency(
        reminder_agent,
        user_context={
            "base_turn_reminder": "Before answering, mention the next follow-up and keep the response actionable.",
        },
    )


def _print_turn_preview(title: str, user_message: str, agency: Agency, include_checkpoint: bool = False) -> None:
    print(f"\n{title}")
    print(json.dumps(preview_turn_input(user_message, agency, include_checkpoint=include_checkpoint), indent=2))


def run_dry_preview() -> None:
    """Preview the reminder-enriched input items without calling the API."""
    agency = create_demo_agency()

    print("System Reminders Demo (dry preview)")
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
    _print_turn_preview(
        "Turn 3: checkpoint reminder",
        "Draft a short customer update for the follow-up.",
        agency,
        include_checkpoint=True,
    )


async def run_live_demo() -> None:
    """Run the reminder pattern against a live model."""
    agency = create_demo_agency()

    print("System Reminders Demo")
    print("=" * 30)

    turns = [
        "Save a follow-up for Acme: send the renewal deck by Friday. Ava owns it.",
        "What follow-up is still open?",
        "Draft a short customer update for the follow-up.",
    ]

    for index, user_message in enumerate(turns, start=1):
        print(f"\nTurn {index}")
        response = await agency.get_response(user_message)
        print(response.final_output)


if __name__ == "__main__":
    if os.getenv("OPENAI_API_KEY"):
        asyncio.run(run_live_demo())
    else:
        run_dry_preview()
