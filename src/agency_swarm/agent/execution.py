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
from agents.items import MessageOutputItem
from agents.stream_events import RawResponsesStreamEvent, StreamEvent
from openai.types.responses import (
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseTextDeltaEvent,
)

from agency_swarm.agent.execution_helpers import (
    cleanup_execution,
    extract_hosted_tool_results_if_needed,
    get_run_trace_id,
    prepare_master_context,
    run_item_to_tresponse_input_item,
    run_with_guardrails,
    setup_execution,
)
from agency_swarm.agent.execution_streaming import StreamingRunResponse, run_stream_with_guardrails
from agency_swarm.messages import (
    MessageFilter,
    MessageFormatter,
)
from agency_swarm.streaming.id_normalizer import StreamIdNormalizer
from agency_swarm.streaming.utils import add_agent_name_to_event
from agency_swarm.utils.citation_extractor import extract_direct_file_annotations
from agency_swarm.utils.model_utils import get_model_name

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
            context_override: Optional context data to override default MasterContext values
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
        try:
            # Process message and file attachments
            # attachment_manager is always initialized in Agent.__init__ via setup_file_manager()
            if self.agent.attachment_manager is None:
                raise RuntimeError(f"attachment_manager not initialized for agent {self.agent.name}")
            processed_current_message_items = await self.agent.attachment_manager.process_message_and_files(
                message, file_ids, kwargs, "get_response"
            )
            # Generate a unique run id for this agent execution (non-streaming)
            current_agent_run_id = f"agent_run_{uuid.uuid4().hex}"

            run_trace_id = get_run_trace_id(run_config_override, agency_context)

            # Prepare history for runner, persisting initiating messages with agent_run_id and parent_run_id
            history_for_runner = MessageFormatter.prepare_history_for_runner(
                processed_current_message_items,
                self.agent,
                sender_name,
                agency_context,
                agent_run_id=current_agent_run_id,
                parent_run_id=parent_run_id,
                run_trace_id=run_trace_id,
            )
            logger.debug(f"Running agent '{self.agent.name}' with history length {len(history_for_runner)}")

            # Prepare context and store reference for potential sync-back
            master_context_for_run = prepare_master_context(self.agent, context_override, agency_context)
            try:
                master_context_for_run._current_agent_run_id = current_agent_run_id
                master_context_for_run._parent_run_id = parent_run_id
            except Exception:
                pass

            agency_name = "Unnamed Agency"
            if agency_context and agency_context.agency_instance:
                agency_name = getattr(agency_context.agency_instance, "name", None) or agency_name

            quick_reply = self._resolve_quick_reply(processed_current_message_items, sender_name)
            if quick_reply is None:
                run_result, master_context_for_run = await run_with_guardrails(
                    agent=self.agent,
                    history_for_runner=history_for_runner,
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
                    validation_attempts=int(getattr(self.agent, "validation_attempts", 1) or 0),
                    throw_input_guardrail_error=getattr(self.agent, "throw_input_guardrail_error", False),
                )
            else:
                assistant_message_id = f"msg_{uuid.uuid4().hex}"
                assistant_item = self._build_quick_reply_item(quick_reply, assistant_message_id)
                run_result = RunResult(
                    input=history_for_runner,
                    new_items=[assistant_item],
                    raw_responses=[],
                    final_output=quick_reply,
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
                    main_model_name = get_model_name(self.agent.model)
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

            # Always save response items (both user and agent-to-agent calls)
            if agency_context and agency_context.thread_manager and run_result.new_items:
                items_to_save: list[TResponseInputItem] = []
                logger.debug(f"Preparing to save {len(run_result.new_items)} new items from RunResult")

                # Only extract hosted tool results if hosted tools were actually used
                hosted_tool_outputs = extract_hosted_tool_results_if_needed(
                    self.agent,
                    run_result.new_items,
                    sender_name,
                )

                # Extract direct file annotations from assistant messages
                assistant_messages = [item for item in run_result.new_items if isinstance(item, MessageOutputItem)]
                citations_by_message = (
                    extract_direct_file_annotations(assistant_messages, agent_name=self.agent.name)
                    if assistant_messages
                    else {}
                )

                current_agent_name = self.agent.name

                for i, run_item_obj in enumerate(run_result.new_items):
                    item_dict = run_item_to_tresponse_input_item(
                        run_item_obj
                    )  # Convert RunItems to TResponseInputItems
                    if item_dict:
                        MessageFormatter.add_citations_to_message(run_item_obj, item_dict, citations_by_message)

                        # Add agency metadata to the response items
                        formatted_item = MessageFormatter.add_agency_metadata(
                            item_dict,
                            agent=current_agent_name,
                            caller_agent=sender_name,
                            agent_run_id=current_agent_run_id,
                            parent_run_id=parent_run_id,
                            run_trace_id=run_trace_id,
                        )
                        items_to_save.append(formatted_item)
                        content_preview = str(item_dict.get("content", ""))[:50]
                        logger.debug(
                            f"  [NewItem #{i}] type={type(run_item_obj).__name__}, "
                            f"role={item_dict.get('role')}, content_preview='{content_preview}...'"
                        )

                        # If this item indicates a handoff, update current agent for subsequent items
                        if getattr(run_item_obj, "type", None) == "handoff_output_item":
                            target = MessageFormatter.extract_handoff_target_name(run_item_obj)
                            if target:
                                current_agent_name = target

                items_to_save.extend(hosted_tool_outputs)
                filtered_items = MessageFilter.filter_messages(items_to_save)  # type: ignore[arg-type] # Filter out unwanted message types

                normalizer = StreamIdNormalizer()
                normalized_items = normalizer.normalize_message_dicts(filtered_items)

                agency_context.thread_manager.add_messages(normalized_items)  # type: ignore[arg-type] # Save filtered items to flat storage
                logger.debug(f"Saved {len(filtered_items)} items to storage (filtered from {len(items_to_save)}).")

            # Sync back context changes if we used a merged context due to override
            if context_override and agency_context and agency_context.agency_instance:
                base_user_context = getattr(agency_context.agency_instance, "user_context", {})
                # Sync back any new keys that weren't part of the original override
                for key, value in master_context_for_run.user_context.items():
                    if key not in context_override:  # Don't sync back override keys
                        base_user_context[key] = value

            return run_result

        finally:
            # Cleanup execution state
            if "master_context_for_run" in locals() and master_context_for_run is not None:  # type: ignore[used-before-def]
                cleanup_execution(
                    self.agent, original_instructions, context_override, agency_context, master_context_for_run
                )
            else:
                # Ensure instructions are restored even if context was not prepared
                self.agent.instructions = original_instructions

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
            context_override: Optional context data to override default MasterContext values
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

                history_for_runner = MessageFormatter.prepare_history_for_runner(
                    processed_current_message_items,
                    self.agent,
                    sender_name,
                    agency_context,
                    agent_run_id=current_agent_run_id,
                    parent_run_id=parent_run_id,
                    run_trace_id=run_trace_id,
                )

                logger.debug(
                    "Starting streaming run for agent '%s' with %d history items.",
                    self.agent.name,
                    len(history_for_runner),
                )

                quick_reply = self._resolve_quick_reply(processed_current_message_items, sender_name)
                if quick_reply is not None:
                    master_context_for_run = prepare_master_context(self.agent, context_override, agency_context)
                    try:
                        master_context_for_run._current_agent_run_id = current_agent_run_id
                        master_context_for_run._parent_run_id = parent_run_id
                    except Exception:
                        pass

                    assistant_message_id = f"msg_{uuid.uuid4().hex}"
                    assistant_item = self._build_quick_reply_item(quick_reply, assistant_message_id)
                    run_result = RunResult(
                        input=history_for_runner,
                        new_items=[assistant_item],
                        raw_responses=[],
                        final_output=quick_reply,
                        input_guardrail_results=[],
                        output_guardrail_results=[],
                        tool_input_guardrail_results=[],
                        tool_output_guardrail_results=[],
                        context_wrapper=RunContextWrapper(master_context_for_run),
                        _last_agent=self.agent,
                    )

                    main_model_name = get_model_name(self.agent.model)
                    if main_model_name:
                        typing.cast(_UsageTrackingRunResult, run_result)._main_agent_model = main_model_name

                    if agency_context:
                        self._persist_quick_reply_message(
                            agency_context=agency_context,
                            run_item=assistant_item,
                            sender_name=sender_name,
                            agent_run_id=current_agent_run_id,
                            parent_run_id=parent_run_id,
                            run_trace_id=run_trace_id,
                        )

                    async for quick_reply_event in self._stream_quick_reply_events(
                        response_text=quick_reply,
                        message_id=assistant_message_id,
                        sender_name=sender_name,
                        agent_run_id=current_agent_run_id,
                        parent_run_id=parent_run_id,
                    ):
                        yield quick_reply_event

                    wrapper._resolve_final_result(typing.cast(RunResultStreaming, run_result))
                    return

                agency_name = "Unnamed Agency"
                if agency_context and agency_context.agency_instance:
                    agency_name = getattr(agency_context.agency_instance, "name", None) or agency_name

                master_context_for_run = prepare_master_context(self.agent, context_override, agency_context)

                stream_handle = run_stream_with_guardrails(
                    agent=self.agent,
                    initial_history_for_runner=history_for_runner,
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
                    validation_attempts=int(getattr(self.agent, "validation_attempts", 1) or 0),
                    throw_input_guardrail_error=getattr(self.agent, "throw_input_guardrail_error", False),
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
                        self.agent, original_instructions, context_override, agency_context, master_context_for_run
                    )
                else:
                    self.agent.instructions = original_instructions
                if self.agent.attachment_manager is None:
                    raise RuntimeError(f"attachment_manager not initialized for agent {self.agent.name}")
                self.agent.attachment_manager.attachments_cleanup()

                if stream_handle is None and wrapper.final_result is None:
                    wrapper._resolve_final_result(None)

        wrapper = StreamingRunResponse(_stream())
        return wrapper

    @staticmethod
    def _normalize_quick_reply_text(text: str) -> str:
        return text.strip().casefold()

    @classmethod
    def _extract_user_text(cls, items: list[TResponseInputItem]) -> str | None:
        for item in reversed(items):
            if not isinstance(item, dict):
                continue
            if item.get("role") != "user":
                continue
            content = item.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                text_chunks: list[str] = []
                for content_item in content:
                    if not isinstance(content_item, dict):
                        continue
                    if content_item.get("type") != "input_text":
                        continue
                    text_value = content_item.get("text")
                    if isinstance(text_value, str):
                        text_chunks.append(text_value)
                if text_chunks:
                    return "".join(text_chunks)
        return None

    def _resolve_quick_reply(self, items: list[TResponseInputItem], sender_name: str | None) -> str | None:
        if sender_name is not None:
            return None
        quick_replies = self.agent.quick_replies
        if not quick_replies:
            return None
        message_text = self._extract_user_text(items)
        if message_text is None:
            return None
        normalized_message = self._normalize_quick_reply_text(message_text)
        if not normalized_message:
            return None
        for reply in quick_replies:
            prompt = reply["prompt"]
            if normalized_message == self._normalize_quick_reply_text(prompt):
                return reply["response"]
        return None

    def _build_quick_reply_item(self, response_text: str, message_id: str) -> MessageOutputItem:
        output_message = ResponseOutputMessage(
            id=message_id,
            content=[ResponseOutputText(text=response_text, type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        )
        return MessageOutputItem(raw_item=output_message, type="message_output_item", agent=self.agent)

    async def _stream_quick_reply_events(
        self,
        *,
        response_text: str,
        message_id: str,
        sender_name: str | None,
        agent_run_id: str | None,
        parent_run_id: str | None,
    ) -> AsyncGenerator[StreamEvent]:
        sequence_number = 1
        start_message = ResponseOutputMessage(
            id=message_id,
            content=[ResponseOutputText(text="", type="output_text", annotations=[])],
            role="assistant",
            status="in_progress",
            type="message",
        )
        added_event = ResponseOutputItemAddedEvent(
            item=start_message,
            output_index=0,
            sequence_number=sequence_number,
            type="response.output_item.added",
        )
        sequence_number += 1
        raw_added = RawResponsesStreamEvent(data=added_event)
        yield add_agent_name_to_event(
            raw_added,
            self.agent.name,
            sender_name,
            agent_run_id=agent_run_id,
            parent_run_id=parent_run_id,
        )

        for delta in response_text:
            text_event = ResponseTextDeltaEvent(
                content_index=0,
                delta=delta,
                item_id=message_id,
                logprobs=[],
                output_index=0,
                sequence_number=sequence_number,
                type="response.output_text.delta",
            )
            sequence_number += 1
            raw_delta = RawResponsesStreamEvent(data=text_event)
            yield add_agent_name_to_event(
                raw_delta,
                self.agent.name,
                sender_name,
                agent_run_id=agent_run_id,
                parent_run_id=parent_run_id,
            )

        completed_message = ResponseOutputMessage(
            id=message_id,
            content=[ResponseOutputText(text=response_text, type="output_text", annotations=[])],
            role="assistant",
            status="completed",
            type="message",
        )
        done_event = ResponseOutputItemDoneEvent(
            item=completed_message,
            output_index=0,
            sequence_number=sequence_number,
            type="response.output_item.done",
        )
        raw_done = RawResponsesStreamEvent(data=done_event)
        yield add_agent_name_to_event(
            raw_done,
            self.agent.name,
            sender_name,
            agent_run_id=agent_run_id,
            parent_run_id=parent_run_id,
        )

    def _persist_quick_reply_message(
        self,
        *,
        agency_context: "AgencyContext",
        run_item: MessageOutputItem,
        sender_name: str | None,
        agent_run_id: str | None,
        parent_run_id: str | None,
        run_trace_id: str,
    ) -> None:
        if not agency_context.thread_manager:
            return
        item_dict = run_item_to_tresponse_input_item(run_item)
        if not item_dict:
            return

        citations_by_message = extract_direct_file_annotations([run_item], agent_name=self.agent.name)
        MessageFormatter.add_citations_to_message(run_item, item_dict, citations_by_message)
        formatted_item = MessageFormatter.add_agency_metadata(
            item_dict,
            agent=self.agent.name,
            caller_agent=sender_name,
            agent_run_id=agent_run_id,
            parent_run_id=parent_run_id,
            run_trace_id=run_trace_id,
        )
        filtered_items = MessageFilter.filter_messages([formatted_item])
        if not filtered_items:
            return
        normalizer = StreamIdNormalizer()
        normalized_items = normalizer.normalize_message_dicts(filtered_items)
        agency_context.thread_manager.add_messages(normalized_items)
