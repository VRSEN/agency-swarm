import asyncio
import json
from textwrap import dedent
from typing import Any, cast

from agents import TResponseInputItem
from agents.memory.openai_responses_compaction_session import is_openai_model_name
from openai import omit
from openai.types.responses import Response

from agency_swarm import Agency, Agent
from agency_swarm.agent.agency_session import COMPACTION_RETAINED_ORIGIN, create_agency_session
from agency_swarm.agent.constants import FRAMEWORK_DEFAULT_MODEL
from agency_swarm.utils.model_utils import get_default_settings_model_name

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
    return FRAMEWORK_DEFAULT_MODEL


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
    if model_name.startswith(("gpt-5.6-", "gpt-6-")):
        response: Response = client.responses.create(model=model_name, input=final_prompt, reasoning={"effort": "none"})
    else:
        response = client.responses.create(model=model_name, input=final_prompt)

    summary_text = response.output_text
    prefixed = "System summary (generated via /compact to keep context comprehensive and focused).\n\n" + summary_text

    summary_message: TResponseInputItem = cast(
        TResponseInputItem,
        {"role": "system", "content": prefixed, "message_origin": "thread_summary"},
    )
    return summary_message


async def compact_thread_items(agency_instance: Agency, args: list[str]) -> list[TResponseInputItem]:
    """Return the compacted replacement for the whole thread.

    When every conversation runs on an OpenAI model, each conversation (the user thread and every
    agent-to-agent thread) is compacted with the Responses API compact endpoint, as the Agents SDK
    does. Otherwise the thread is replaced by a single model-written summary message.
    """
    if not agency_instance.entry_points:
        raise RuntimeError("Agency has no entry points; configure at least one entry agent.")
    conversations = _conversations(agency_instance)
    if not all(_responses_compact_model(agent) for agent, _caller in conversations):
        return [await compact_thread(agency_instance, args)]

    instructions = " ".join(args) or None
    compacted = await asyncio.gather(
        *(_compact_conversation(agency_instance, agent, caller, instructions) for agent, caller in conversations)
    )
    return [item for conversation in compacted for item in conversation]


def _conversations(agency_instance: Agency) -> list[tuple[Agent, str | None]]:
    """The user thread, then each (recipient, caller) agent-to-agent thread in first-seen order."""
    conversations: list[tuple[Agent, str | None]] = [(agency_instance.entry_points[0], None)]
    for message in agency_instance.thread_manager.get_all_messages():
        record = cast(dict[str, Any], message)
        caller, recipient = record.get("callerAgent"), record.get("agent")
        if caller is None or recipient not in agency_instance.agents:
            continue
        if all((agent.name, known_caller) != (recipient, caller) for agent, known_caller in conversations):
            conversations.append((agency_instance.agents[recipient], caller))
    return conversations


def _responses_compact_model(agent: Agent) -> str | None:
    model_name = get_default_settings_model_name(agent.model)
    return model_name if model_name and is_openai_model_name(model_name) else None


async def _compact_conversation(
    agency_instance: Agency, agent: Agent, caller: str | None, instructions: str | None
) -> list[TResponseInputItem]:
    session = create_agency_session(
        agent=agent,
        sender_name=caller,
        agency_context=agency_instance.get_agent_context(agent.name),
        new_input_items=[],
        agent_run_id=None,
        parent_run_id=None,
        run_trace_id=None,
        run_config_override=None,
    )
    # The same history the model would receive on the next turn.
    history = await session.get_items()
    if not history:
        return []
    compacted = await agent.client.responses.compact(
        model=cast(str, _responses_compact_model(agent)),
        input=cast(Any, history),
        instructions=instructions if instructions is not None else omit,
    )
    items: list[TResponseInputItem] = []
    for output_item in compacted.output:
        # responses.compact returns user messages with input_text parts inside output-message models.
        item = output_item.model_dump(exclude_unset=True, warnings=False)
        item.pop("created_by", None)
        item["agent"] = agent.name
        item["callerAgent"] = caller
        if item.get("type") != "compaction":
            item["message_origin"] = COMPACTION_RETAINED_ORIGIN
        items.append(cast(TResponseInputItem, item))
    return items
