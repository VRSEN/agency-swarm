from typing import TYPE_CHECKING, Any

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    TResponseInputItem,
)

from agency_swarm.messages import MessageFormatter

if TYPE_CHECKING:
    from .context_types import AgencyContext
    from .core import Agent


def _extract_guardrail_texts(e: BaseException) -> tuple[Any, str]:
    """Return (assistant_output, guidance_text) from a guardrail exception."""
    assistant_output: Any = None
    guidance_text: str = ""
    try:
        guardrail_result = getattr(e, "guardrail_result", None)
        if guardrail_result is not None:
            assistant_output = getattr(guardrail_result, "agent_output", None)
            output_obj = getattr(guardrail_result, "output", None)
            if output_obj is not None:
                guidance_text = str(getattr(output_obj, "output_info", ""))
    except Exception:
        pass
    if assistant_output is None:
        assistant_output = str(e)
    if not guidance_text:
        guidance_text = str(e)
    return assistant_output, guidance_text


def append_guardrail_feedback(
    *,
    agent: "Agent",
    agency_context: "AgencyContext | None",
    sender_name: str | None,
    parent_run_id: str | None,
    current_agent_run_id: str,
    exception: BaseException,
    include_assistant: bool,
) -> list[TResponseInputItem]:
    """Persist guardrail feedback messages and rebuild history for retry.

    Restores message_origin metadata consistent with previous behavior while
    keeping refactored structure. This enables downstream consumers to
    differentiate guidance provenance.
    """
    assistant_output, guidance_text = _extract_guardrail_texts(exception)

    if agency_context and agency_context.thread_manager:
        to_persist: list[TResponseInputItem] = []
        if include_assistant:
            assistant_msg: TResponseInputItem = {  # type: ignore[typeddict-item]
                "role": "assistant",
                "content": assistant_output,
            }
            to_persist.append(
                MessageFormatter.add_agency_metadata(
                    assistant_msg,
                    agent=agent.name,
                    caller_agent=sender_name,
                    agent_run_id=current_agent_run_id,
                    parent_run_id=parent_run_id,
                )
            )

        # Preserve prior metadata: classify the guidance message origin
        if isinstance(exception, OutputGuardrailTripwireTriggered):
            origin = "output_guardrail_error"
        elif isinstance(exception, InputGuardrailTripwireTriggered) and getattr(
            agent, "throw_input_guardrail_error", False
        ):
            origin = "input_guardrail_error"
        else:
            origin = "input_guardrail_message"

        guidance_msg: TResponseInputItem = {  # type: ignore[assignment, typeddict-item, typeddict-unknown-key]
            "role": "system",
            "content": guidance_text,
            "message_origin": origin,  # type: ignore[typeddict-unknown-key]
        }
        to_persist.append(
            MessageFormatter.add_agency_metadata(
                guidance_msg,
                agent=agent.name,
                caller_agent=sender_name,
                agent_run_id=current_agent_run_id,
                parent_run_id=parent_run_id,
            )
        )

        agency_context.thread_manager.add_messages(to_persist)  # type: ignore[arg-type]

    # Rebuild full history for retry using persisted messages
    return MessageFormatter.prepare_history_for_runner(
        [],
        agent,
        sender_name,
        agency_context,
        agent_run_id=current_agent_run_id,
        parent_run_id=parent_run_id,
    )
