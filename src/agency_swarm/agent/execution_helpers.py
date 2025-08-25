import inspect
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agents.items import RunItem, ToolCallItem, TResponseInputItem
from openai.types.responses import ResponseFileSearchToolCall, ResponseFunctionWebSearch

from agency_swarm.context import MasterContext
from agency_swarm.messages import MessageFormatter

if TYPE_CHECKING:
    from agency_swarm.agent.core import AgencyContext, Agent

logger = logging.getLogger(__name__)


def run_item_to_tresponse_input_item(item: RunItem) -> TResponseInputItem | None:
    """
    Converts a RunItem from a RunResult into TResponseInputItem dictionary format for history.
    """
    try:
        # Use the SDK's built-in conversion method instead of manual conversion
        converted_item = item.to_input_item()
        logger.debug(f"Converting {type(item).__name__} using SDK to_input_item(): {converted_item}")
        return converted_item

    except Exception as e:
        logger.warning(f"Failed to convert {type(item).__name__} using to_input_item(): {e}")
        return None


def prepare_master_context(
    agent: "Agent", context_override: dict[str, Any] | None, agency_context: "AgencyContext | None" = None
) -> MasterContext:
    """Constructs the MasterContext for the current run."""
    if not agency_context or not agency_context.thread_manager:
        raise RuntimeError("Cannot prepare context: AgencyContext with ThreadManager required.")

    thread_manager = agency_context.thread_manager
    agency_instance = agency_context.agency_instance

    # For standalone agent usage (no agency), create minimal context
    if not agency_instance or not hasattr(agency_instance, "agents"):
        return MasterContext(
            thread_manager=thread_manager,
            agents={agent.name: agent},  # Only include self
            user_context=context_override or {},
            current_agent_name=agent.name,
            shared_instructions=agency_context.shared_instructions,
        )

    # Use reference for persistence, or create merged copy if override provided
    base_user_context = getattr(agency_instance, "user_context", {})
    user_context = {**base_user_context, **context_override} if context_override else base_user_context

    return MasterContext(
        thread_manager=thread_manager,
        agents=agency_instance.agents,
        user_context=user_context,
        current_agent_name=agent.name,
        shared_instructions=agency_context.shared_instructions,
    )


def extract_hosted_tool_results_if_needed(agent: "Agent", run_items: list[RunItem]) -> list[TResponseInputItem]:
    """
    Optimized version that only extracts hosted tool results if hosted tools were actually used.
    This prevents expensive parsing on every response when no hosted tools exist.
    """
    # Quick check: do we have any hosted tool calls?
    has_hosted_tools = any(
        isinstance(item, ToolCallItem)
        and isinstance(item.raw_item, ResponseFileSearchToolCall | ResponseFunctionWebSearch)
        for item in run_items
    )

    # Log debugging info for file search
    for item in run_items:
        if isinstance(item, ToolCallItem):
            logger.debug(f"ToolCallItem type: {type(item.raw_item).__name__}")
            if hasattr(item.raw_item, "name"):
                logger.debug(f"  Tool name: {item.raw_item.name}")

    if not has_hosted_tools:
        logger.debug("No hosted tool calls found in run_items")
        return []  # Early exit - no hosted tools used

    return MessageFormatter.extract_hosted_tool_results(agent, run_items)


def setup_execution(
    agent: "Agent",
    sender_name: str | None,
    agency_context: "AgencyContext | None",
    additional_instructions: str | None,
    method_name: str = "execution",
) -> str | Callable | None:
    """Common setup logic for both get_response and get_response_stream."""
    # Validate agency instance exists if this is agent-to-agent communication
    _validate_agency_for_delegation(agent, sender_name, agency_context)

    # Store original instructions for restoration
    original_instructions = agent.instructions

    # Temporarily modify instructions if additional_instructions provided
    if additional_instructions:
        if not isinstance(additional_instructions, str):
            raise ValueError("additional_instructions must be a string")
        logger.debug(f"Appending additional instructions to agent '{agent.name}': {additional_instructions[:100]}...")
        if isinstance(agent.instructions, str) and agent.instructions:
            # Only append if it's a non-empty string
            agent.instructions = agent.instructions + "\n\n" + additional_instructions
        elif callable(agent.instructions):
            # Create a wrapper function that calls original callable and appends additional instructions
            original_callable = agent.instructions

            async def combined_instructions(run_context, agent_instance):
                # Call the original callable instructions (handle both sync and async)
                if inspect.iscoroutinefunction(original_callable):
                    base_instructions = await original_callable(run_context, agent_instance)
                else:
                    base_instructions = original_callable(run_context, agent_instance)

                # Append additional instructions
                if base_instructions:
                    return base_instructions + "\n\n" + additional_instructions
                else:
                    return additional_instructions

            agent.instructions = combined_instructions
        else:
            # Replace if it's None or empty string
            agent.instructions = additional_instructions

    # Log the conversation context
    logger.info(f"Agent '{agent.name}' handling {method_name} from sender: {sender_name}")

    return original_instructions


def _validate_agency_for_delegation(
    agent: "Agent", sender_name: str | None, agency_context: "AgencyContext | None" = None
) -> None:
    """Validate that agency context exists if delegation is needed."""
    # If this is agent-to-agent communication, we need an agency context with a valid agency
    if sender_name is not None:
        if not agency_context:
            raise RuntimeError(
                f"Agent '{agent.name}' missing AgencyContext for agent-to-agent communication. "
                f"Agent-to-agent communication requires an Agency to manage the context."
            )

        agency_instance = agency_context.agency_instance
        if not agency_instance:
            raise RuntimeError(
                f"Agent '{agent.name}' received agent-to-agent message from '{sender_name}' but is running "
                f"in standalone mode. Agent-to-agent communication requires agents to be managed by an Agency."
            )

        if not hasattr(agency_instance, "agents"):
            raise RuntimeError(f"Agent '{agent.name}' has invalid Agency instance for agent-to-agent communication.")


def cleanup_execution(
    agent: "Agent",
    original_instructions: str | Callable | None,
    context_override: dict[str, Any] | None,
    agency_context: "AgencyContext | None",
    master_context_for_run: MasterContext,
) -> None:
    """Common cleanup logic for execution methods."""
    # Sync back context changes if we used a merged context due to override
    if context_override and agency_context and agency_context.agency_instance:
        base_user_context = getattr(agency_context.agency_instance, "user_context", {})
        # Sync back any new keys that weren't part of the original override
        for key, value in master_context_for_run.user_context.items():
            if key not in context_override:  # Don't sync back override keys
                base_user_context[key] = value

    # Always restore original instructions
    agent.instructions = original_instructions
