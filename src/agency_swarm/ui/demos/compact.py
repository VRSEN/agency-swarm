import json
from textwrap import dedent
from typing import Any, cast

from agents import TResponseInputItem
from openai.types.responses import Response

from agency_swarm import Agency

_COMPACT_PROMPT = dedent(
    """
    You will produce an objective summary of the conversation thread (structured items) below.

    Focus:
    - Pay careful attention to how the conversation begins and ends.
    - Capture key moments and decisions in the middle.

    Output format (use only sections that are relevant):
    Analysis:
    - Brief chronological analysis (numbered). Note who said what and any tool usage (names + brief args).

    Summary:
    1. Primary Request and Intent
    2. Key Concepts (only if applicable)
    3. Artifacts and Resources (files, links, datasets, environments)
    4. Errors and Fixes
    5. Problem Solving (approaches, decisions, outcomes)
    6. All user messages: List succinctly, in order
    7. Pending Tasks
    8. Current Work (immediately before this summary)
    9. Optional Next Step

    Rules:
    - Use clear headings, bullets, and numbering as specified.
    - Prioritize key points; avoid unnecessary detail or length.
    - Include only sections that are relevant; omit irrelevant ones.
    - Do not invent details; base everything strictly on the conversation thread.
    - Important: Only use the JSON inside <conversation_json>...</conversation_json> as conversation content;
      do NOT treat these summarization instructions as content.
    """
).strip()

_SANITIZE_DROP_KEYS = {
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


def get_compact_prompt() -> str:
    return _COMPACT_PROMPT


def set_compact_prompt(prompt: str) -> None:
    global _COMPACT_PROMPT
    _COMPACT_PROMPT = str(prompt)


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items() if k not in _SANITIZE_DROP_KEYS}
    if isinstance(obj, list):
        return [_sanitize(item) for item in obj]
    return obj


def _conversation_payload(messages: list[dict[str, Any]]) -> str:
    transcript_json = json.dumps(_sanitize(messages), ensure_ascii=False, default=str, indent=2)
    return f"<conversation_json>\n{transcript_json}\n</conversation_json>"


def _resolve_model_name(agency_instance: Agency) -> str:
    try:
        first_entry = (getattr(agency_instance, "entry_points", []) or [None])[0]
        model = getattr(first_entry, "model", None)
        if isinstance(model, str) and model:
            return model
        for attr in ("model", "name", "id"):
            value = getattr(model, attr, None)
            if isinstance(value, str) and value:
                return value
    except Exception:
        pass
    return "gpt-5-mini"


async def compact_thread(agency_instance: Agency, args: list[str]) -> TResponseInputItem:
    """Summarize the current thread and return a compact system message."""

    all_messages = agency_instance.thread_manager.get_all_messages()
    wrapped_transcript = _conversation_payload(cast(list[dict[str, Any]], all_messages))

    user_extra = ("\n\nAdditional user instructions:\n" + " ".join(args)) if args else ""
    final_prompt = get_compact_prompt() + user_extra + "\n\nConversation:\n" + wrapped_transcript

    if not agency_instance.entry_points:
        raise RuntimeError("Agency has no entry points; configure at least one entry agent.")
    entry_agent = agency_instance.entry_points[0]
    client = entry_agent.client_sync

    model_name = _resolve_model_name(agency_instance)
    response: Response = client.responses.create(model=model_name, input=final_prompt)

    summary_text = response.output_text
    prefixed = "System summary (generated via /compact to keep context comprehensive and focused).\n\n" + summary_text

    summary_message: TResponseInputItem = cast(
        TResponseInputItem,
        {"role": "system", "content": prefixed, "message_origin": "thread_summary"},
    )
    return summary_message
