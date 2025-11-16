from typing import TYPE_CHECKING, cast

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    TResponseInputItem,
)

from agency_swarm.messages import MessageFormatter

if TYPE_CHECKING:
    from .context_types import AgencyContext
    from .core import Agent


def extract_guardrail_texts(e: BaseException) -> tuple[list[TResponseInputItem], str]:
    """Return (assistant_output, guidance_text) from a guardrail exception."""
    assistant_output: list[TResponseInputItem] = []
    guidance_text: str = ""
    try:
        guardrail_result = getattr(e, "guardrail_result", None)
        if guardrail_result is not None:
            run_data = getattr(e, "run_data", None)
            if run_data is not None:
                assistant_output = [item.to_input_item() for item in run_data.new_items]

            if not assistant_output:
                agent_output = getattr(guardrail_result, "agent_output", None)
                if isinstance(agent_output, list):
                    assistant_output = [
                        cast(TResponseInputItem, item)
                        if isinstance(item, dict)
                        else cast(
                            TResponseInputItem,
                            {
                                "role": "assistant",
                                "content": str(item),
                            },
                        )
                        for item in agent_output
                    ]
                elif isinstance(agent_output, dict):
                    assistant_output = [cast(TResponseInputItem, agent_output)]
                elif agent_output is not None:
                    assistant_output = [
                        cast(
                            TResponseInputItem,
                            {
                                "role": "assistant",
                                "content": str(agent_output),
                            },
                        )
                    ]

            output_obj = getattr(guardrail_result, "output", None)
            if output_obj is not None:
                guidance_text = str(getattr(output_obj, "output_info", ""))
    except Exception:
        pass
    if not assistant_output:
        assistant_output = [
            {
                "role": "assistant",
                "content": str(e),
            }
        ]
    if not guidance_text:
        guidance_text = str(e)
    return assistant_output, guidance_text


def append_guardrail_feedback(
    *,
    agent: "Agent",
    agency_context: "AgencyContext | None",
    sender_name: str | None,
    parent_run_id: str | None,
    run_trace_id: str,
    current_agent_run_id: str,
    exception: BaseException,
    include_assistant: bool,
) -> list[TResponseInputItem]:
    """Persist guardrail feedback messages and rebuild history for retry.

    Restores message_origin metadata consistent with previous behavior while
    keeping refactored structure. This enables downstream consumers to
    differentiate guidance provenance.
    """
    assistant_output, guidance_text = extract_guardrail_texts(exception)

    if agency_context and agency_context.thread_manager:
        to_persist: list[TResponseInputItem] = []
        if include_assistant:
            for item in assistant_output:
                to_persist.append(
                    MessageFormatter.add_agency_metadata(
                        item,
                        agent=agent.name,
                        caller_agent=sender_name,
                        agent_run_id=current_agent_run_id,
                        parent_run_id=parent_run_id,
                        run_trace_id=run_trace_id,
                    )
                )

        # Preserve prior metadata: classify the guidance message origin
        if isinstance(exception, OutputGuardrailTripwireTriggered):
            origin = "output_guardrail_error"
            message_role = "system"
        elif isinstance(exception, InputGuardrailTripwireTriggered) and getattr(
            agent, "throw_input_guardrail_error", False
        ):
            origin = "input_guardrail_error"
            message_role = "system"
        else:
            origin = "input_guardrail_message"
            message_role = "assistant"

        guidance_msg: TResponseInputItem = {  # type: ignore[assignment, typeddict-item, typeddict-unknown-key]
            "role": message_role,
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
                run_trace_id=run_trace_id,
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
        run_trace_id=run_trace_id,
    )
