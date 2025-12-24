# --- Agency response methods ---
import asyncio
import contextvars
import logging
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from .core import Agency

from agents import RunConfig, RunHooks, RunResult, TResponseInputItem

from agency_swarm.agent.core import Agent
from agency_swarm.agent.execution_streaming import StreamingRunResponse
from agency_swarm.tools.mcp_manager import attach_persistent_mcp_servers

from .helpers import get_agent_context, resolve_agent

logger = logging.getLogger(__name__)


async def get_response(
    agency: "Agency",
    message: str | list[TResponseInputItem],
    recipient_agent: str | Agent | None = None,
    context_override: dict[str, Any] | None = None,
    hooks_override: RunHooks | None = None,
    run_config: RunConfig | None = None,
    message_files: list[str] | None = None,
    file_ids: list[str] | None = None,
    additional_instructions: str | None = None,
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
        message_files (list[str] | None, optional): Backward compatibility parameter.
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
    agency_context = get_agent_context(agency, target_agent.name)

    # On handoffs all servers need to be initialized to be used
    await attach_persistent_mcp_servers(agency)

    return await target_agent.get_response(
        message=message,
        sender_name=None,
        context_override=context_override,
        hooks_override=effective_hooks,
        run_config_override=run_config,
        message_files=message_files,
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
    message_files: list[str] | None = None,
    file_ids: list[str] | None = None,
    additional_instructions: str | None = None,
    **kwargs: Any,
) -> RunResult:
    """Synchronous wrapper around :meth:`get_response`."""

    def _coro():
        return get_response(
            agency,
            message=message,
            recipient_agent=recipient_agent,
            context_override=context_override,
            hooks_override=hooks_override,
            run_config=run_config,
            message_files=message_files,
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
    message_files: list[str] | None = None,
    file_ids: list[str] | None = None,
    additional_instructions: str | None = None,
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
        message_files (list[str] | None, optional): Backward compatibility parameter.
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
                enhanced_context["_streaming_context"] = streaming_context

                agency_context = get_agent_context(agency, target_agent.name)

                await attach_persistent_mcp_servers(agency)

                primary_stream = target_agent.get_response_stream(
                    message=message,
                    sender_name=None,
                    context_override=enhanced_context,
                    hooks_override=effective_hooks,
                    run_config_override=run_config_override,
                    message_files=message_files,
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
