import asyncio
import logging
import typing
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from agents import (
    RunConfig,
    RunContextWrapper,
    RunHooks,
    RunResult,
    RunResultStreaming,
    TResponseInputItem,
)
from agents.stream_events import StreamEvent

from agency_swarm.agent.agency_session import create_agency_session
from agency_swarm.agent.conversation_starters_cache import (
    build_run_items_from_cached,
    compute_starter_cache_fingerprint,
    extract_final_output_text,
    extract_starter_segment,
    filter_replay_items,
    is_simple_text_message,
    load_cached_starter,
    match_conversation_starter,
    merge_cacheable_starters,
    normalize_starter_text,
    parse_cached_output,
    prepare_cached_items_for_replay,
    reorder_cached_items_for_tools,
    save_cached_starter,
)
from agency_swarm.agent.conversation_starters_streaming import stream_cached_items_events
from agency_swarm.agent.execution_helpers import (
    cleanup_execution,
    extract_hosted_tool_results_if_needed,
    get_run_trace_id,
    prepare_master_context,
    run_with_guardrails,
    setup_execution,
)
from agency_swarm.agent.execution_streaming import StreamingRunResponse, run_stream_with_guardrails
from agency_swarm.messages import (
    MessageFilter,
)
from agency_swarm.streaming.id_normalizer import StreamIdNormalizer
from agency_swarm.utils.model_utils import get_usage_tracking_model_name

if TYPE_CHECKING:
    from agents.items import ModelResponse

    from agency_swarm.agent.core import AgencyContext, Agent
DEFAULT_MAX_TURNS = 1000000  # Unlimited by default

logger = logging.getLogger(__name__)


class _UsageTrackingRunResult(typing.Protocol):
    _sub_agent_responses_with_model: list[tuple[str | None, "ModelResponse"]]
    _main_agent_model: str


class Execution:
    def __init__(self, agent: "Agent"):
        self.agent = agent

    async def get_response(
        self,
        message: str | list[TResponseInputItem],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        agency_context: "AgencyContext | None" = None,
        parent_run_id: str | None = None,  # Parent agent's execution ID
        **kwargs: Any,
    ) -> RunResult:
        """
        Runs the agent's turn in the conversation loop, handling both user and agent-to-agent interactions.
        Runs the agent using the `agents.Runner` to get the response, validate it, and save the results.

        Args:
            message: The input message as a string or structured input items list
            sender_name: Name of the sending agent (None for user interactions)
            context_override: Run-scoped context passed into MasterContext.user_context
            hooks_override: Optional hooks to override default agent hooks
            run_config_override: Optional run configuration settings
            file_ids: List of OpenAI file IDs to attach to the message
            additional_instructions: Additional instructions to be appended to
                the agent's instructions for this run only
            **kwargs: Additional keyword arguments including max_turns

        Returns:
            RunResult: The complete execution result
        """
        logger.info(f"Agent '{self.agent.name}' starting run.")

        # Common setup and validation
        original_instructions = setup_execution(
            self.agent, sender_name, agency_context, additional_instructions, "get_response"
        )

        master_context_for_run = None
        run_result: RunResult | None = None
        try:
            if self.agent.attachment_manager is None:
                raise RuntimeError(f"attachment_manager not initialized for agent {self.agent.name}")
            processed_current_message_items = await self.agent.attachment_manager.process_message_and_files(
                message, file_ids, kwargs, "get_response"
            )
            # Generate a unique run id for this agent execution (non-streaming)
            current_agent_run_id = f"agent_run_{uuid.uuid4().hex}"

            run_trace_id = get_run_trace_id(run_config_override, agency_context)

            initial_saved_count = 0
            if agency_context and agency_context.thread_manager:
                try:
                    initial_saved_count = len(agency_context.thread_manager.get_all_messages())
                except Exception:
                    initial_saved_count = 0
            is_first_message = initial_saved_count == 0

            # Build the SDK session over the shared store; the SDK owns history
            # prepend and turn persistence from here on.
            session = create_agency_session(
                agent=self.agent,
                sender_name=sender_name,
                agency_context=agency_context,
                new_input_items=processed_current_message_items,
                agent_run_id=current_agent_run_id,
                parent_run_id=parent_run_id,
                run_trace_id=run_trace_id,
                run_config_override=run_config_override,
            )
            logger.debug(f"Running agent '{self.agent.name}' with history length {len(session.prepared_input())}")

            # Prepare context and store reference for potential sync-back
            master_context_for_run = prepare_master_context(self.agent, context_override, agency_context)
            try:
                master_context_for_run._current_agent_run_id = current_agent_run_id
                master_context_for_run._parent_run_id = parent_run_id
            except Exception:
                pass

            agency_name = "Unnamed Agency"
            if agency_context and agency_context.agency_instance is not None:
                from agency_swarm.agency.core import Agency

                agency_instance = agency_context.agency_instance
                if isinstance(agency_instance, Agency):
                    agency_instance_name = agency_instance.name
                    if isinstance(agency_instance_name, str):
                        agency_name = agency_instance_name

            matched_starter: str | None = None
            cached_starter = None
            cache_fingerprint: str | None = None
            cacheable_starters = merge_cacheable_starters(
                self.agent.conversation_starters if self.agent.cache_conversation_starters else None,
                self.agent.quick_replies,
                self.agent.system_reminders,
            )
            has_user_context_override = bool(
                context_override and any(key != "streaming_context" for key in context_override)
            )
            if (
                sender_name is None
                and cacheable_starters
                and is_first_message
                and is_simple_text_message(processed_current_message_items)
                and not additional_instructions  # Skip cache when per-run instructions provided
                and not has_user_context_override  # Skip cache when per-run context provided
                and hooks_override is None  # Skip cache when hooks override is provided
            ):
                runtime_state = agency_context.runtime_state if agency_context else None
                shared_instructions = agency_context.shared_instructions if agency_context else None
                cache_fingerprint = compute_starter_cache_fingerprint(
                    self.agent,
                    runtime_state=runtime_state,
                    shared_instructions=shared_instructions,
                    instructions_override=original_instructions,
                    use_instructions_override=True,
                )
                matched_starter = match_conversation_starter(processed_current_message_items, cacheable_starters)
                if matched_starter:
                    normalized = normalize_starter_text(matched_starter)
                    cache_map = self.agent._conversation_starters_cache
                    cached_starter = cache_map.get(normalized)
                    if (
                        cached_starter is not None
                        and cache_fingerprint
                        and cached_starter.metadata.get("fingerprint") != cache_fingerprint
                    ):
                        cached_starter = None
                    if cached_starter is None:
                        cached_starter = load_cached_starter(
                            self.agent.name,
                            matched_starter,
                            expected_fingerprint=cache_fingerprint,
                        )
                        if cached_starter is not None:
                            cache_map[normalized] = cached_starter

            if cached_starter is None:
                run_result, master_context_for_run = await run_with_guardrails(
                    agent=self.agent,
                    input_items=processed_current_message_items,
                    session=session,
                    master_context_for_run=master_context_for_run,
                    sender_name=sender_name,
                    agency_context=agency_context,
                    hooks_override=hooks_override,
                    run_config_override=run_config_override
                    or RunConfig(workflow_name=agency_name, trace_id=run_trace_id),
                    kwargs=kwargs,
                    current_agent_run_id=current_agent_run_id,
                    parent_run_id=parent_run_id,
                    run_trace_id=run_trace_id,
                    validation_attempts=int(self.agent.validation_attempts or 0),
                    raise_input_guardrail_error=self.agent.raise_input_guardrail_error,
                )
            else:
                replay_items = prepare_cached_items_for_replay(
                    cached_starter.items,
                    run_trace_id=run_trace_id,
                    parent_run_id=parent_run_id,
                )
                replay_items = filter_replay_items(replay_items)
                run_items = build_run_items_from_cached(self.agent, replay_items)
                final_output_text = extract_final_output_text(replay_items)
                final_output = parse_cached_output(final_output_text, self.agent.output_type)
                # No SDK run happens on the cached path; the input was persisted at
                # session creation, so only the replayed items need storing here.
                # Snapshot the model input before the replay lands in the store so
                # RunResult.input keeps legacy semantics (history + new input only).
                result_input = session.prepared_input()
                session.persist_items(replay_items)
                run_result = RunResult(
                    input=result_input,
                    new_items=run_items,
                    raw_responses=[],
                    final_output=final_output,
                    input_guardrail_results=[],
                    output_guardrail_results=[],
                    tool_input_guardrail_results=[],
                    tool_output_guardrail_results=[],
                    context_wrapper=RunContextWrapper(master_context_for_run),
                    _last_agent=self.agent,
                )

            # Store sub-agent raw_responses with model info for per-response cost calculation
            # These are tuples of (model_name, response) to enable accurate per-model pricing
            if run_result and master_context_for_run:
                try:
                    sub_raw_responses = master_context_for_run._sub_agent_raw_responses
                    if sub_raw_responses:
                        # Store on run_result for access during cost calculation
                        typed_run_result = typing.cast(_UsageTrackingRunResult, run_result)
                        typed_run_result._sub_agent_responses_with_model = list(sub_raw_responses)
                        # Clear after copying to avoid duplicates
                        master_context_for_run._sub_agent_raw_responses.clear()
                except Exception as e:
                    logger.debug(f"Could not store sub-agent raw_responses on RunResult: {e}")

            # Store main agent's model on run_result for automatic cost calculation
            if run_result:
                try:
                    main_model_name = get_usage_tracking_model_name(self.agent.model)
                    if main_model_name:
                        typing.cast(_UsageTrackingRunResult, run_result)._main_agent_model = main_model_name
                except Exception as e:
                    logger.debug(f"Could not store main agent model on RunResult: {e}")

            completion_info = (
                f"Output Type: {type(run_result.final_output).__name__}"
                if run_result.final_output is not None
                else "No final output"
            )
            logger.info(
                f"Agent '{self.agent.name}' completed run. New Items: {len(run_result.new_items)}, {completion_info}"
            )

            # Turn items are persisted by the SDK through the AgencySession; only
            # synthetic hosted-tool outputs (not part of model history) are appended here.
            if agency_context and agency_context.thread_manager and run_result.new_items:
                hosted_tool_outputs = extract_hosted_tool_results_if_needed(
                    self.agent,
                    run_result.new_items,
                    sender_name,
                )
                if hosted_tool_outputs:
                    filtered_items = MessageFilter.filter_messages(hosted_tool_outputs)  # type: ignore[arg-type]
                    normalizer = StreamIdNormalizer()
                    normalized_items = normalizer.normalize_message_dicts(filtered_items)
                    agency_context.thread_manager.add_messages(normalized_items)  # type: ignore[arg-type]
                    logger.debug(f"Saved {len(normalized_items)} hosted tool output items to storage.")

            if (
                matched_starter
                and cached_starter is None
                and is_first_message
                and agency_context
                and agency_context.thread_manager
            ):
                try:
                    all_messages = agency_context.thread_manager.get_all_messages()
                    new_messages = all_messages[initial_saved_count:]
                    segment = extract_starter_segment(new_messages, matched_starter) or new_messages
                    if segment and extract_final_output_text(segment):
                        segment = reorder_cached_items_for_tools(segment, self.agent.name)
                        cached = save_cached_starter(
                            self.agent.name,
                            matched_starter,
                            segment,
                            metadata={"source": "live_run"},
                            fingerprint=cache_fingerprint,
                        )
                        cache_map = self.agent._conversation_starters_cache
                        cache_map[normalize_starter_text(matched_starter)] = cached
                except Exception as e:
                    logger.debug(f"Failed to cache conversation starter: {e}")

            # Legacy sync-back of context changes runs once in cleanup_execution (finally block below).
            return run_result

        finally:
            # Cleanup execution state
            if "master_context_for_run" in locals() and master_context_for_run is not None:  # type: ignore[used-before-def]
                cleanup_execution(
                    self.agent,
                    original_instructions,
                    context_override,
                    agency_context,
                    master_context_for_run,
                    run_result,
                )
            else:
                # Ensure instructions are restored even if context was not prepared
                self.agent.instructions = original_instructions
            if self.agent.attachment_manager is None:
                raise RuntimeError(f"attachment_manager not initialized for agent {self.agent.name}")
            self.agent.attachment_manager.attachments_cleanup()

    def get_response_stream(
        self,
        message: str | list[TResponseInputItem],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        agency_context: "AgencyContext | None" = None,
        parent_run_id: str | None = None,  # Parent agent's execution ID
        **kwargs: Any,
    ) -> StreamingRunResponse:
        """
        Streams the agent's response turn-by-turn, yielding events as they occur.

        Returns a :class:`StreamingRunResponse` that can be iterated to consume stream
        events while also exposing the final :class:`RunResultStreaming` when available.

        Args:
            message: The input message as a string or structured input items list
            sender_name: Name of the sending agent (None for user interactions)
            context_override: Run-scoped context passed into MasterContext.user_context
            hooks_override: Optional hooks to override default agent hooks
            run_config_override: Optional run configuration settings
            file_ids: List of OpenAI file IDs to attach to the message
            additional_instructions: Additional instructions to be appended to
                the agent's instructions for this run only
            **kwargs: Additional keyword arguments including max_turns

        Returns:
            StreamingRunResponse: Async iterable yielding stream events and exposing the
            final run result.
        """

        async def _error_stream(error_message: str) -> AsyncGenerator[dict[str, str]]:
            yield {"type": "error", "content": error_message}

        if message is None:
            logger.error("message cannot be None")
            error_wrapper = StreamingRunResponse(_error_stream("message cannot be None"))
            error_wrapper._resolve_final_result(None)
            return error_wrapper
        if isinstance(message, str) and not message.strip():
            logger.error("message cannot be empty")
            error_wrapper = StreamingRunResponse(_error_stream("message cannot be empty"))
            error_wrapper._resolve_final_result(None)
            return error_wrapper

        logger.info(f"Agent '{self.agent.name}' starting streaming run.")

        wrapper: StreamingRunResponse

        async def _stream() -> AsyncGenerator[StreamEvent | dict[str, Any]]:
            nonlocal wrapper

            original_instructions = setup_execution(
                self.agent, sender_name, agency_context, additional_instructions, "get_response_stream"
            )

            master_context_for_run = None
            stream_handle: StreamingRunResponse | None = None

            try:
                if self.agent.attachment_manager is None:
                    raise RuntimeError(f"attachment_manager not initialized for agent {self.agent.name}")
                processed_current_message_items = await self.agent.attachment_manager.process_message_and_files(
                    message, file_ids, kwargs, "get_response_stream"
                )
                current_agent_run_id = f"agent_run_{uuid.uuid4().hex}"

                run_trace_id = get_run_trace_id(run_config_override, agency_context)

                initial_saved_count = 0
                if agency_context and agency_context.thread_manager:
                    try:
                        initial_saved_count = len(agency_context.thread_manager.get_all_messages())
                    except Exception:
                        initial_saved_count = 0
                is_first_message = initial_saved_count == 0

                session = create_agency_session(
                    agent=self.agent,
                    sender_name=sender_name,
                    agency_context=agency_context,
                    new_input_items=processed_current_message_items,
                    agent_run_id=current_agent_run_id,
                    parent_run_id=parent_run_id,
                    run_trace_id=run_trace_id,
                    run_config_override=run_config_override,
                )

                logger.debug(
                    "Starting streaming run for agent '%s' with %d history items.",
                    self.agent.name,
                    len(session.prepared_input()),
                )

                matched_starter: str | None = None
                cached_starter = None
                cache_fingerprint: str | None = None
                cacheable_starters = merge_cacheable_starters(
                    self.agent.conversation_starters if self.agent.cache_conversation_starters else None,
                    self.agent.quick_replies,
                    self.agent.system_reminders,
                )
                has_user_context_override = bool(
                    context_override and any(key != "streaming_context" for key in context_override)
                )
                if (
                    sender_name is None
                    and cacheable_starters
                    and is_first_message
                    and is_simple_text_message(processed_current_message_items)
                    and not additional_instructions  # Skip cache when per-run instructions provided
                    and not has_user_context_override  # Skip cache when per-run context provided
                    and hooks_override is None  # Skip cache when hooks override is provided
                ):
                    runtime_state = agency_context.runtime_state if agency_context else None
                    shared_instructions = agency_context.shared_instructions if agency_context else None
                    cache_fingerprint = compute_starter_cache_fingerprint(
                        self.agent,
                        runtime_state=runtime_state,
                        shared_instructions=shared_instructions,
                        instructions_override=original_instructions,
                        use_instructions_override=True,
                    )
                    matched_starter = match_conversation_starter(processed_current_message_items, cacheable_starters)
                    if matched_starter:
                        normalized = normalize_starter_text(matched_starter)
                        cache_map = self.agent._conversation_starters_cache
                        cached_starter = cache_map.get(normalized)
                        if (
                            cached_starter is not None
                            and cache_fingerprint
                            and cached_starter.metadata.get("fingerprint") != cache_fingerprint
                        ):
                            cached_starter = None
                        if cached_starter is None:
                            cached_starter = load_cached_starter(
                                self.agent.name,
                                matched_starter,
                                expected_fingerprint=cache_fingerprint,
                            )
                            if cached_starter is not None:
                                cache_map[normalized] = cached_starter

                if cached_starter is not None:
                    master_context_for_run = prepare_master_context(self.agent, context_override, agency_context)
                    try:
                        master_context_for_run._current_agent_run_id = current_agent_run_id
                        master_context_for_run._parent_run_id = parent_run_id
                    except Exception:
                        pass

                    replay_items = prepare_cached_items_for_replay(
                        cached_starter.items,
                        run_trace_id=run_trace_id,
                        parent_run_id=parent_run_id,
                    )
                    replay_items = filter_replay_items(replay_items)
                    # No SDK run happens on the cached path; the input was persisted
                    # at session creation, so only the replayed items need storing.
                    # Snapshot the model input before the replay lands in the store
                    # so RunResult.input keeps legacy semantics (history + new input).
                    result_input = session.prepared_input()
                    session.persist_items(replay_items)

                    run_items = build_run_items_from_cached(self.agent, replay_items)
                    final_output_text = extract_final_output_text(replay_items)
                    final_output = parse_cached_output(final_output_text, self.agent.output_type)
                    run_result = RunResult(
                        input=result_input,
                        new_items=run_items,
                        raw_responses=[],
                        final_output=final_output,
                        input_guardrail_results=[],
                        output_guardrail_results=[],
                        tool_input_guardrail_results=[],
                        tool_output_guardrail_results=[],
                        context_wrapper=RunContextWrapper(master_context_for_run),
                        _last_agent=self.agent,
                    )

                    main_model_name = get_usage_tracking_model_name(self.agent.model)
                    if main_model_name:
                        typing.cast(_UsageTrackingRunResult, run_result)._main_agent_model = main_model_name

                    async for cached_event in stream_cached_items_events(items=replay_items, agent=self.agent):
                        yield cached_event

                    wrapper._resolve_final_result(typing.cast(RunResultStreaming, run_result))
                    return

                agency_name = "Unnamed Agency"
                if agency_context and agency_context.agency_instance is not None:
                    from agency_swarm.agency.core import Agency

                    agency_instance = agency_context.agency_instance
                    if isinstance(agency_instance, Agency):
                        agency_instance_name = agency_instance.name
                        if isinstance(agency_instance_name, str):
                            agency_name = agency_instance_name

                master_context_for_run = prepare_master_context(self.agent, context_override, agency_context)

                stream_handle = run_stream_with_guardrails(
                    agent=self.agent,
                    initial_input_items=processed_current_message_items,
                    session=session,
                    master_context_for_run=master_context_for_run,
                    sender_name=sender_name,
                    agency_context=agency_context,
                    hooks_override=hooks_override,
                    run_config_override=run_config_override
                    or RunConfig(workflow_name=agency_name, trace_id=run_trace_id),
                    kwargs=kwargs,
                    current_agent_run_id=current_agent_run_id,
                    parent_run_id=parent_run_id,
                    run_trace_id=run_trace_id,
                    validation_attempts=int(self.agent.validation_attempts or 0),
                    raise_input_guardrail_error=self.agent.raise_input_guardrail_error,
                )

                if isinstance(stream_handle, StreamingRunResponse):
                    wrapper._adopt_stream(stream_handle)

                async for event in stream_handle:
                    yield event
            except asyncio.CancelledError:
                wrapper._resolve_final_result(None)
                raise
            except Exception as exc:
                wrapper._resolve_exception(exc)
                raise
            finally:
                if master_context_for_run is not None:
                    cleanup_execution(
                        self.agent,
                        original_instructions,
                        context_override,
                        agency_context,
                        master_context_for_run,
                        wrapper.final_result,
                    )
                else:
                    self.agent.instructions = original_instructions
                if (
                    matched_starter
                    and cached_starter is None
                    and is_first_message
                    and agency_context
                    and agency_context.thread_manager
                ):
                    try:
                        all_messages = agency_context.thread_manager.get_all_messages()
                        new_messages = all_messages[initial_saved_count:]
                        segment = extract_starter_segment(new_messages, matched_starter) or new_messages
                        if segment and extract_final_output_text(segment):
                            segment = reorder_cached_items_for_tools(segment, self.agent.name)
                            cached = save_cached_starter(
                                self.agent.name,
                                matched_starter,
                                segment,
                                metadata={"source": "live_stream"},
                                fingerprint=cache_fingerprint,
                            )
                            cache_map = self.agent._conversation_starters_cache
                            cache_map[normalize_starter_text(matched_starter)] = cached
                    except Exception as e:
                        logger.debug(f"Failed to cache conversation starter: {e}")
                if self.agent.attachment_manager is None:
                    raise RuntimeError(f"attachment_manager not initialized for agent {self.agent.name}")
                self.agent.attachment_manager.attachments_cleanup()

                if stream_handle is None and wrapper.final_result is None:
                    wrapper._resolve_final_result(None)

        wrapper = StreamingRunResponse(_stream())
        return wrapper
