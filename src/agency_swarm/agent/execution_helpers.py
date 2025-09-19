import inspect
import logging
from collections.abc import Callable
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any

from agents import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    RunHooks,
    Runner,
    RunResult,
    TResponseInputItem,
)
from agents.exceptions import AgentsException
from agents.items import RunItem, ToolCallItem
from openai.types.responses import (
    ResponseFileSearchToolCall,
    ResponseFunctionWebSearch,
)

from agency_swarm.context import MasterContext
from agency_swarm.messages import MessageFormatter
from agency_swarm.tools.mcp_manager import default_mcp_manager

from .execution_guardrails import _extract_guardrail_texts, append_guardrail_feedback

if TYPE_CHECKING:
    from agency_swarm.agent.core import AgencyContext, Agent

logger = logging.getLogger(__name__)


"""
Execution helpers (non-streaming): split to keep file size under 500 lines.
Streaming helpers moved to execution_streaming.py.
"""


async def perform_single_run(
    *,
    agent: "Agent",
    history_for_runner: list[TResponseInputItem],
    master_context_for_run: MasterContext,
    hooks_override: RunHooks | None,
    run_config_override: RunConfig | None,
    kwargs: dict[str, Any],
) -> RunResult:
    """Execute a single Runner.run with MCP stack setup.

    This is the core execution primitive intentionally separated from guardrail orchestration
    so that tests and future features can reuse the bare run without coupling to retries.
    """
    result: RunResult
    async with AsyncExitStack() as mcp_stack:
        for server in agent.mcp_servers:
            # If server exposes a connected session, skip per-run context management
            if getattr(server, "session", None) is None:
                await default_mcp_manager.ensure_connected(server)
            if getattr(server, "session", None) is None:
                logger.warning(f"Entering async context for server {server.name}")
                await mcp_stack.enter_async_context(server)  # type: ignore[arg-type]

        result = await Runner.run(
            starting_agent=agent,
            input=history_for_runner,
            context=master_context_for_run,
            hooks=hooks_override,
            run_config=run_config_override or RunConfig(),
            max_turns=kwargs.get("max_turns", 1000000),
        )
    return result


# perform_streamed_run moved to execution_streaming.py


async def run_sync_with_guardrails(
    *,
    agent: "Agent",
    history_for_runner: list[TResponseInputItem],
    master_context_for_run: MasterContext,
    sender_name: str | None,
    agency_context: "AgencyContext | None",
    hooks_override: RunHooks | None,
    run_config_override: RunConfig | None,
    kwargs: dict[str, Any],
    current_agent_run_id: str,
    parent_run_id: str | None,
    validation_attempts: int,
    throw_input_guardrail_error: bool,
) -> tuple[RunResult, MasterContext]:
    """Run a single turn with guardrail handling and optional retries."""
    attempts_remaining = int(validation_attempts or 0)
    while True:
        try:
            run_result = await perform_single_run(
                agent=agent,
                history_for_runner=history_for_runner,
                master_context_for_run=master_context_for_run,
                hooks_override=hooks_override,
                run_config_override=run_config_override,
                kwargs=kwargs,
            )
            return run_result, master_context_for_run
        except OutputGuardrailTripwireTriggered as e:
            history_for_runner = append_guardrail_feedback(
                agent=agent,
                agency_context=agency_context,
                sender_name=sender_name,
                parent_run_id=parent_run_id,
                current_agent_run_id=current_agent_run_id,
                exception=e,
                include_assistant=True,
            )
            if attempts_remaining <= 0:
                raise e
            try:
                _assistant_output, _guidance_text = _extract_guardrail_texts(e)
                logger.info(
                    "Output guardrail tripped. attempts_left=%s guidance=%s",
                    attempts_remaining,
                    _guidance_text,
                )
            except Exception:
                logger.info("Output guardrail tripped. attempts_left=%s", attempts_remaining)
            attempts_remaining -= 1
            continue
        except InputGuardrailTripwireTriggered as e:
            history_for_runner = append_guardrail_feedback(
                agent=agent,
                agency_context=agency_context,
                sender_name=sender_name,
                parent_run_id=parent_run_id,
                current_agent_run_id=current_agent_run_id,
                exception=e,
                include_assistant=False,
            )
            if not throw_input_guardrail_error:
                from agents import RunContextWrapper  # local import to avoid cycle

                _, guidance_text = _extract_guardrail_texts(e)
                wrapper = RunContextWrapper(master_context_for_run)
                return (
                    RunResult(
                        input=history_for_runner,
                        new_items=[],
                        raw_responses=[],
                        final_output=guidance_text,
                        input_guardrail_results=(
                            [e.guardrail_result] if getattr(e, "guardrail_result", None) is not None else []
                        ),
                        output_guardrail_results=[],
                        context_wrapper=wrapper,
                        _last_agent=agent,
                    ),
                    master_context_for_run,
                )
            raise e
        except Exception as e:
            raise AgentsException(f"Runner execution failed for agent {agent.name}") from e
        finally:
            if agent.attachment_manager is None:
                raise RuntimeError(f"attachment_manager not initialized for agent {agent.name}")
            agent.attachment_manager.attachments_cleanup()


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


def _resolve_latest_shared_instructions(agency_context: "AgencyContext | None") -> str | None:
    """Return the freshest shared instructions and keep the context in sync."""
    if not agency_context:
        return None

    agency_instance = getattr(agency_context, "agency_instance", None)
    if agency_instance and hasattr(agency_instance, "shared_instructions"):
        latest = getattr(agency_instance, "shared_instructions", None)
        normalized = latest if isinstance(latest, str) else None
        normalized = normalized or None
        agency_context.shared_instructions = normalized
        return normalized

    existing = agency_context.shared_instructions
    if isinstance(existing, str):
        normalized = existing or None
        agency_context.shared_instructions = normalized
        return normalized

    agency_context.shared_instructions = None
    return None


def prepare_master_context(
    agent: "Agent", context_override: dict[str, Any] | None, agency_context: "AgencyContext | None" = None
) -> MasterContext:
    """Constructs the MasterContext for the current run."""
    if not agency_context or not agency_context.thread_manager:
        raise RuntimeError("Cannot prepare context: AgencyContext with ThreadManager required.")

    thread_manager = agency_context.thread_manager
    agency_instance = agency_context.agency_instance
    shared_instructions_for_run = _resolve_latest_shared_instructions(agency_context)

    # For standalone agent usage (no agency), create minimal context
    if not agency_instance or not hasattr(agency_instance, "agents"):
        return MasterContext(
            thread_manager=thread_manager,
            agents={agent.name: agent},  # Only include self
            user_context=context_override or {},
            current_agent_name=agent.name,
            shared_instructions=shared_instructions_for_run,
        )

    # Use reference for persistence, or create merged copy if override provided
    base_user_context = getattr(agency_instance, "user_context", {})
    user_context = {**base_user_context, **context_override} if context_override else base_user_context

    return MasterContext(
        thread_manager=thread_manager,
        agents=agency_instance.agents,
        user_context=user_context,
        current_agent_name=agent.name,
        shared_instructions=shared_instructions_for_run,
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

    # Temporarily modify instructions if shared or additional instructions provided
    shared_instructions_text = _resolve_latest_shared_instructions(agency_context)

    if additional_instructions and not isinstance(additional_instructions, str):
        raise ValueError("additional_instructions must be a string")

    additional_for_run: str | None = additional_instructions or None

    def build_combined_instructions(base_text: str | None) -> str | None:
        """Compose the runtime instructions in the order: shared -> base -> additional."""
        core_parts: list[str] = []
        if shared_instructions_text:
            core_parts.append(shared_instructions_text)
        if base_text:
            core_parts.append(base_text)

        core_instructions = "\n\n".join(core_parts) if core_parts else None
        if not additional_for_run:
            return core_instructions

        separator = "\n\n---\n\n" if shared_instructions_text else "\n\n"
        if core_instructions:
            return f"{core_instructions}{separator}{additional_for_run}"
        return additional_for_run

    # Skip modification if nothing to add
    if shared_instructions_text or additional_for_run:
        logger.debug(
            "Preparing combined instructions for agent '%s' (shared: %s, additional: %s)",
            agent.name,
            bool(shared_instructions_text),
            bool(additional_for_run),
        )

        if isinstance(agent.instructions, str) and agent.instructions:
            combined = build_combined_instructions(agent.instructions)
            if combined is not None:
                agent.instructions = combined
        elif callable(agent.instructions):
            # Create a wrapper function that calls original callable and joins shared/additional instructions
            original_callable = agent.instructions

            async def combined_instructions(run_context, agent_instance):
                # Call the original callable instructions (handle both sync and async)
                if inspect.iscoroutinefunction(original_callable):
                    base_instructions = await original_callable(run_context, agent_instance)
                else:
                    base_instructions = original_callable(run_context, agent_instance)

                base_text = None
                if base_instructions:
                    base_text = str(base_instructions)

                combined = build_combined_instructions(base_text)
                # Fall back to original result if nothing was combined (should be rare)
                return combined if combined is not None else base_instructions

            agent.instructions = combined_instructions
        else:
            # Replace if it's None or unsupported type with the composed shared/additional instructions
            combined = build_combined_instructions(None)
            if combined is not None:
                agent.instructions = combined

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
