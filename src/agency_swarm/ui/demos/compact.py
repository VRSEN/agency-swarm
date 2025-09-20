import json
import logging
from typing import Any, cast

from agents import TResponseInputItem

from agency_swarm import Agency

logger = logging.getLogger(__name__)


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

    # Prompt
    from .launcher import TerminalDemoLauncher  # local import to avoid circulars

    user_extra = ("\n\nAdditional user instructions:\n" + " ".join(args)) if args else ""
    final_prompt = TerminalDemoLauncher.COMPACT_PROMPT + user_extra + "\n\nConversation:\n" + wrapped_transcript

    # Model selection
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

    # Client reuse; require an explicit synchronous client on the entry agent.
    if not agency_instance.entry_points:
        raise RuntimeError("Agency has no entry points; configure at least one entry agent.")
    entry_agent = agency_instance.entry_points[0]
    client = entry_agent.client_sync

    # Minimal reasoning for OpenAI models
    is_openai_model = isinstance(model_name, str) and ("gpt" in model_name.lower())
    if is_openai_model:
        resp = client.responses.create(model=model_name, input=final_prompt, reasoning={"effort": "minimal"})
    else:
        resp = client.responses.create(model=model_name, input=final_prompt)
    if not hasattr(resp, "output_text"):
        raise RuntimeError("Client response missing 'output_text' attribute.")
    summary_text = resp.output_text  # type: ignore[attr-defined]

    prefixed = "System summary (generated via /compact to keep context comprehensive and focused).\n\n" + summary_text
    chat_id = TerminalDemoLauncher.start_new_chat(agency_instance)

    summary_message: dict[str, Any] = {"role": "system", "content": prefixed, "message_origin": "thread_summary"}
    agency_instance.thread_manager.replace_messages(cast(list[TResponseInputItem], [summary_message]))

    return chat_id
