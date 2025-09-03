# --- Deprecated completion methods ---
import asyncio
import logging
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import Agency

from agency_swarm.agent.core import Agent

from .responses import get_response

logger = logging.getLogger(__name__)


async def async_get_completion(
    agency: "Agency",
    message: str,
    message_files: list[str] | None = None,
    yield_messages: bool = False,
    recipient_agent: str | Agent | None = None,
    additional_instructions: str | None = None,
    attachments: list[dict] | None = None,
    tool_choice: dict | None = None,
    verbose: bool = False,
    response_format: dict | None = None,
    **kwargs: Any,
) -> str:
    """
    [INTERNAL ASYNC] Async implementation of get_completion for internal use.
    """
    # Handle deprecated parameters
    if yield_messages:
        raise NotImplementedError(
            "yield_messages=True is not yet implemented in v1.x. "
            "Use get_response_stream() instead for streaming responses."
        )

    if attachments:
        warnings.warn(
            "'attachments' parameter is deprecated. Use 'message_files' or 'file_ids' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # TODO: Convert attachments format to file_ids if needed
        raise NotImplementedError(
            "attachments parameter conversion is not yet implemented. Use 'message_files' or 'file_ids' instead."
        )

    if tool_choice:
        raise NotImplementedError(
            "tool_choice parameter is not yet implemented in v1.x. TODO: Implement tool_choice support in get_response."
        )

    if verbose:
        logger.warning("verbose parameter is deprecated and ignored. Use logging configuration instead.")

    if response_format:
        raise NotImplementedError(
            "response_format parameter is no longer supported. "
            "Use the 'output_type' parameter on the Agent instead for structured outputs."
        )

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

    # Call the new get_response method with backward compatibility
    run_result = await get_response(
        agency,
        message=message,
        recipient_agent=target_recipient,
        message_files=message_files,  # Pass deprecated parameter for compatibility
        additional_instructions=additional_instructions,  # Pass additional_instructions parameter
        **kwargs,
    )
    return str(run_result.final_output) if run_result.final_output is not None else ""


def get_completion(
    agency: "Agency",
    message: str,
    message_files: list[str] | None = None,
    yield_messages: bool = False,
    recipient_agent: str | Agent | None = None,
    additional_instructions: str | None = None,
    attachments: list[dict] | None = None,
    tool_choice: dict | None = None,
    verbose: bool = False,
    response_format: dict | None = None,
    **kwargs: Any,
) -> str:
    """
    [DEPRECATED] Use get_response instead. Returns final text output.
    """
    warnings.warn(
        "get_completion is deprecated. Use get_response instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Use asyncio.run to call the async method from sync context
    return asyncio.run(
        async_get_completion(
            agency,
            message=message,
            message_files=message_files,
            yield_messages=yield_messages,
            recipient_agent=recipient_agent,
            additional_instructions=additional_instructions,
            attachments=attachments,
            tool_choice=tool_choice,
            verbose=verbose,
            response_format=response_format,
            **kwargs,
        )
    )


def get_completion_stream(agency: "Agency", *args: Any, **kwargs: Any):
    """
    [DEPRECATED] Use get_response_stream instead. Yields all events from the modern streaming API.
    """
    warnings.warn(
        "get_completion_stream is deprecated. Use get_response_stream instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    raise NotImplementedError("get_completion_stream is not yet implemented in v1.x. Use get_response_stream instead.")
