import json
import uuid
from typing import Any

from openai import OpenAI

from agency_swarm import Agency


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

    # Client reuse
    try:
        entry_agent = (getattr(agency_instance, "entry_points", []) or [None])[0]
        client = getattr(entry_agent, "client_sync", OpenAI())
    except Exception:
        client = OpenAI()

    # Minimal reasoning for OpenAI models
    is_openai_model = isinstance(model_name, str) and ("gpt" in model_name.lower())
    if is_openai_model:
        resp = client.responses.create(model=model_name, input=final_prompt, reasoning={"effort": "minimal"})
    else:
        resp = client.responses.create(model=model_name, input=final_prompt)
    summary_text = getattr(resp, "output_text", "") or str(resp)

    # Replace thread with summary
    agency_instance.thread_manager.clear()
    chat_id = f"run_demo_chat_{uuid.uuid4()}"
    prefixed = "System summary (generated via /compact to keep context comprehensive and focused).\n\n" + summary_text
    agency_instance.thread_manager.add_message(
        {"role": "system", "content": prefixed, "message_origin": "thread_summary"}  # type: ignore[arg-type]
    )

    # Persist
    TerminalDemoLauncherRef = __import__(
        "agency_swarm.ui.demos.launcher", fromlist=["TerminalDemoLauncher"]
    ).TerminalDemoLauncher
    TerminalDemoLauncherRef.save_current_chat(agency_instance, chat_id)
    return chat_id
