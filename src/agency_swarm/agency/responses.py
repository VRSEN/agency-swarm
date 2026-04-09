# --- Agency response methods ---
import asyncio
import contextvars
import logging
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from agency_swarm.agent.context_types import AgencyContext

    from .core import Agency

from agents import RunConfig, RunHooks, RunResult, TResponseInputItem

from agency_swarm.agent.core import Agent
from agency_swarm.agent.execution_streaming import StreamingRunResponse
from agency_swarm.tools.mcp_manager import attach_persistent_mcp_servers

from .helpers import get_agent_context, resolve_agent

logger = logging.getLogger(__name__)

_CONTROL_REMINDER_ORIGINS = frozenset({"handoff_reminder", "recipient_reminder"})


def _get_last_user_call_messages(messages: list[TResponseInputItem]) -> list[TResponseInputItem]:
    """Return messages for the most recent user-initiated call and its leading control reminders."""
    last_user_index = -1
    for index, message in enumerate(messages):
        if isinstance(message, dict) and message.get("role") == "user" and message.get("callerAgent") is None:
            last_user_index = index
    if last_user_index < 0:
        return []

    start_index = last_user_index
    run_id = None
    last_user_message = messages[last_user_index]
    if isinstance(last_user_message, dict):
        candidate_run_id = last_user_message.get("agent_run_id")
        if isinstance(candidate_run_id, str) and candidate_run_id:
            run_id = candidate_run_id

    while start_index > 0:
        previous = messages[start_index - 1]
        if not isinstance(previous, dict):
            break

        if run_id is not None and previous.get("agent_run_id") == run_id:
            start_index -= 1
            continue

        if previous.get("message_origin") not in _CONTROL_REMINDER_ORIGINS:
            break
        start_index -= 1

    return messages[start_index:]


def _should_add_recipient_switch_reminder(
    *,
    agency_context: "AgencyContext | None",
    target_agent_name: str,
) -> bool:
    """Return whether to prepend a recipient-switch reminder for this user turn."""
    if agency_context is None or agency_context.thread_manager is None:
        return False

    last_call_messages = _get_last_user_call_messages(agency_context.thread_manager.get_all_messages())
    if not last_call_messages:
        return False

    top_level_run_ids = {
        run_id
        for message in last_call_messages
        if isinstance(message, dict)
        and message.get("callerAgent") is None
        and isinstance(run_id := message.get("agent_run_id"), str)
    }
    used_control_reminder = any(
        isinstance(message, dict)
        and message.get("message_origin") in _CONTROL_REMINDER_ORIGINS
        and message.get("callerAgent") is None
        and (
            message.get("agent_run_id") in top_level_run_ids
            if top_level_run_ids and message.get("agent_run_id") is not None
            else True
        )
        for message in last_call_messages
    )
    if not used_control_reminder:
        return False

    for message in reversed(last_call_messages):
        if isinstance(message, dict):
            message_dict = cast(dict[str, Any], message)
            if (
                message_dict.get("role") == "assistant"
                and message_dict.get("callerAgent") is None
                and isinstance(message_dict.get("agent"), str)
            ):
                return cast(str, message_dict["agent"]) != target_agent_name

    return True


def _build_user_message_with_recipient_reminder(
    message: str | list[TResponseInputItem],
    *,
    target_agent: Agent,
) -> list[TResponseInputItem]:
    """Return input items with a recipient-switch reminder prepended."""
    description = (target_agent.description or "").strip()
    reminder_content = f'User has switched recipient agent. You are "{target_agent.name}".'
    if description:
        reminder_content += f" Role: {description}"
        if description[-1] not in ".!?":
            reminder_content += "."
    reminder_content += " Please continue the task."

    reminder = cast(
        TResponseInputItem,
        {
            "role": "system",
            "content": reminder_content,
            "message_origin": "recipient_reminder",
        },
    )

    if isinstance(message, list):
        return [reminder, *message]

    return [reminder, cast(TResponseInputItem, {"role": "user", "content": message})]


async def get_response(
    agency: "Agency",
    message: str | list[TResponseInputItem],
    recipient_agent: str | Agent | None = None,
    context_override: dict[str, Any] | None = None,
    hooks_override: RunHooks | None = None,
    run_config: RunConfig | None = None,
    file_ids: list[str] | None = None,
    additional_instructions: str | None = None,
    agency_context_override: "AgencyContext | None" = None,
    **kwargs: Any,
) -> RunResult:
    """
    Initiates an interaction with a specified agent within the agency.

    This method resolves the target agent, validates if it's a designated entry point
    (logs warning if not), determines the appropriate hooks (user override or agency default
    persistence hooks), and delegates the actual execution to the target agent's `get_response` method.

    Args:
        message (str | list[dict[str, Any]]): The input message for the agent.
        recipient_agent (str | Agent | None, optional): The target agent instance or its name.
                                                       If None, defaults to the first entry point agent.
        context_override (dict[str, Any] | None, optional): Additional context to pass to the agent run.
        hooks_override (RunHooks | None, optional): Specific hooks to use for this run, overriding
                                                   agency-level persistence hooks.
        run_config (RunConfig | None, optional): Configuration for the agent run.
        file_ids (list[str] | None, optional): Additional file IDs for the agent run.
        additional_instructions (str | None, optional): Additional instructions to be appended to the recipient
            agent's instructions for this run only.
        **kwargs: Additional arguments passed down to the target agent's `get_response` method
                  and subsequently to `agents.Runner.run`.

    Returns:
        RunResult: The result of the agent execution chain initiated by this call.

    Raises:
        ValueError: If the specified `recipient_agent` name is not found or the instance
                    is not part of this agency, or if no recipient_agent is specified and
                    no entry points are available.
        TypeError: If `recipient_agent` is not a string or an `Agent` instance.
        AgentsException: If errors occur during the underlying agent execution.
    """
    # Determine recipient agent - default to first entry point if not specified
    target_recipient = recipient_agent
    if target_recipient is None:
        if agency.entry_points:
            target_recipient = agency.entry_points[0]
            logger.debug(f"No recipient_agent specified, using first entry point: {target_recipient.name}")
        else:
            raise ValueError(
                "No recipient_agent specified and no entry points available. "
                "Specify recipient_agent or ensure agency has entry points."
            )

    target_agent = resolve_agent(agency, target_recipient)

    effective_hooks = hooks_override or agency.persistence_hooks

    # Get agency context for the target agent (stateless context passing)
    agency_context = agency_context_override or get_agent_context(agency, target_agent.name)

    # On handoffs all servers need to be initialized to be used
    await attach_persistent_mcp_servers(agency)

    message_for_call: str | list[TResponseInputItem] = message
    if _should_add_recipient_switch_reminder(agency_context=agency_context, target_agent_name=target_agent.name):
        message_for_call = _build_user_message_with_recipient_reminder(message, target_agent=target_agent)

    return await target_agent.get_response(
        message=message_for_call,
        sender_name=None,
        context_override=context_override,
        hooks_override=effective_hooks,
        run_config_override=run_config,
        file_ids=file_ids,
        additional_instructions=additional_instructions,
        agency_context=agency_context,  # Pass stateless context
        **kwargs,
    )


def get_response_sync(
    agency: "Agency",
    message: str | list[TResponseInputItem],
    recipient_agent: str | Agent | None = None,
    context_override: dict[str, Any] | None = None,
    hooks_override: RunHooks | None = None,
    run_config: RunConfig | None = None,
    file_ids: list[str] | None = None,
    additional_instructions: str | None = None,
    agency_context_override: "AgencyContext | None" = None,
    **kwargs: Any,
) -> RunResult:
    """Synchronous wrapper around :meth:`get_response`."""

    def _coro():
        return get_response(
            agency,
            message=message,
            recipient_agent=recipient_agent,
            context_override=context_override,
            agency_context_override=agency_context_override,
            hooks_override=hooks_override,
            run_config=run_config,
            file_ids=file_ids,
            additional_instructions=additional_instructions,
            **kwargs,
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_coro())

    result_future: Future[RunResult] = Future()
    caller_context = contextvars.copy_context()

    def _runner() -> None:
        try:
            result = caller_context.run(lambda: asyncio.run(_coro()))
            result_future.set_result(cast(RunResult, result))
        except BaseException as exc:
            result_future.set_exception(exc)

    thread = threading.Thread(
        target=_runner,
        name="agency-get-response-sync",
        daemon=True,
    )
    thread.start()

    return result_future.result()


def get_response_stream(
    agency: "Agency",
    message: str | list[TResponseInputItem],
    recipient_agent: str | Agent | None = None,
    context_override: dict[str, Any] | None = None,
    hooks_override: RunHooks | None = None,
    run_config_override: RunConfig | None = None,
    file_ids: list[str] | None = None,
    additional_instructions: str | None = None,
    agency_context_override: "AgencyContext | None" = None,
    **kwargs: Any,
) -> StreamingRunResponse:
    """
    Initiates a streaming interaction with a specified agent within the agency.

    Returns a :class:`StreamingRunResponse` wrapper that yields merged events from the
    primary agent and any delegated sub-agents while exposing the final
    ``RunResultStreaming`` once available.

    Args:
        message (str | list[dict[str, Any]]): The input message for the agent.
        recipient_agent (str | Agent | None, optional): The target agent instance or its name.
                                                       If None, defaults to the first entry point agent.
        context_override (dict[str, Any] | None, optional): Additional context for the run.
        hooks_override (RunHooks | None, optional): Specific hooks for this run.
        run_config_override (RunConfig | None, optional): Specific run configuration for this run.
        file_ids (list[str] | None, optional): Additional file IDs for the agent run.
        additional_instructions (str | None, optional): Additional instructions to be appended to the recipient
            agent's instructions for this run only.
        **kwargs: Additional arguments passed down to `get_response_stream` and `run_streamed`.

    Raises:
        ValueError: If the specified `recipient_agent` is not found, or if no recipient_agent
                    is specified and no entry points are available.
        TypeError: If `recipient_agent` is not a string or `Agent` instance.
        AgentsException: If errors occur during setup or execution.
    """
    wrapper: StreamingRunResponse

    async def _agency_stream() -> Any:
        nonlocal wrapper

        target_recipient = recipient_agent
        if target_recipient is None:
            if agency.entry_points:
                target_recipient = agency.entry_points[0]
                logger.debug(
                    "No recipient_agent specified for stream, using first entry point: %s",
                    target_recipient.name,
                )
            else:
                raise ValueError(
                    "No recipient_agent specified and no entry points available. "
                    "Specify recipient_agent or ensure agency has entry points."
                )

        target_agent = resolve_agent(agency, target_recipient)

        effective_hooks = hooks_override or agency.persistence_hooks

        try:
            async with agency.event_stream_merger.create_streaming_context() as streaming_context:
                enhanced_context = context_override.copy() if context_override else {}
                enhanced_context["streaming_context"] = streaming_context

                agency_context = agency_context_override or get_agent_context(agency, target_agent.name)

                await attach_persistent_mcp_servers(agency)

                message_for_call: str | list[TResponseInputItem] = message
                if isinstance(message, str) and not message.strip():
                    message_for_call = message
                elif _should_add_recipient_switch_reminder(
                    agency_context=agency_context,
                    target_agent_name=target_agent.name,
                ):
                    message_for_call = _build_user_message_with_recipient_reminder(message, target_agent=target_agent)

                primary_stream = target_agent.get_response_stream(
                    message=message_for_call,
                    sender_name=None,
                    context_override=enhanced_context,
                    hooks_override=effective_hooks,
                    run_config_override=run_config_override,
                    file_ids=file_ids,
                    additional_instructions=additional_instructions,
                    agency_context=agency_context,
                    **kwargs,
                )

                if isinstance(primary_stream, StreamingRunResponse):
                    wrapper._adopt_stream(primary_stream)

                async for event in agency.event_stream_merger.merge_streams(primary_stream, streaming_context):
                    yield event
        except asyncio.CancelledError:
            wrapper._resolve_final_result(None)
            raise
        except Exception as exc:
            wrapper._resolve_exception(exc)
            raise
        finally:
            if not wrapper._has_inner_stream() and wrapper.final_result is None:
                wrapper._resolve_final_result(None)

    wrapper = StreamingRunResponse(_agency_stream())
    return wrapper
