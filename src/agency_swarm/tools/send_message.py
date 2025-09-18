"""
Defines the SendMessage and SendMessageHandoff tools for direct communication between agents.

This module provides the `SendMessage` class, a specialized `FunctionTool` that
allows one agent to send a message to another registered agent within the
Agency Swarm framework. The tool is dynamically configured with sender and
recipient details.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Literal

from agents import FunctionTool, InputGuardrailTripwireTriggered, RunContextWrapper, handoff, strict_schema
from pydantic import BaseModel, ValidationError

from ..context import MasterContext
from ..streaming.utils import add_agent_name_to_event

if TYPE_CHECKING:
    from ..agent.core import AgencyContext, Agent

logger = logging.getLogger(__name__)


class SendMessage(FunctionTool):
    """
    Use this tool to facilitate direct, synchronous communication between specialized agents within your agency.

    When you send a message using this tool, you receive a response exclusively from the designated recipient
    agent. To continue the dialogue, invoke this tool again with the desired recipient agent and your follow-up
    message. Remember, communication here is synchronous; the recipient agent won't perform any tasks post-response.

    You are responsible for relaying the recipient agent's responses back to the user, as the user does not have
    direct access to these replies. Keep engaging with the tool for continuous interaction until the task is fully
    resolved. Do not send more than 1 message to the same recipient agent at the same time.
    """

    sender_agent: "Agent"
    # Dict mapping lowercase recipient names to Agent instances
    recipients: dict[str, "Agent"]
    # Track recipients with pending messages (thread-safe)
    _pending_recipients: set[str]
    # Lock to protect concurrent access to _pending_recipients
    _pending_lock: asyncio.Lock

    def __init__(
        self,
        sender_agent: "Agent",
        recipients: dict[str, "Agent"] | None = None,
        name: str = "send_message",
    ):
        self.sender_agent = sender_agent
        # Normalize recipient keys to lowercase for case-insensitive lookup
        self.recipients = {k.lower(): v for k, v in (recipients or {}).items()}
        # Initialize tracking set for pending recipients
        self._pending_recipients = set()
        # Create lock for thread-safe access
        self._pending_lock = asyncio.Lock()

        # Build the recipient agent enum values for the schema
        recipient_names = list(self.recipients.values())
        recipient_enum = [agent.name for agent in recipient_names] if recipient_names else []

        # Rich parameter schema incorporating all field descriptions
        params_schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "recipient_agent": {
                    "type": "string",
                    "enum": recipient_enum,
                    "description": "The name of the agent to send the message to.",
                },
                "my_primary_instructions": {
                    "type": "string",
                    "description": (
                        "Please repeat your primary instructions step-by-step, including both completed "
                        "and the following next steps that you need to perform. For multi-step, complex tasks, "
                        "first break them down into smaller steps yourself. Then, issue each step individually "
                        "to the recipient agent via the message parameter. Each identified step should be "
                        "sent in a separate message. Keep in mind that the recipient agent does not have access "
                        "to these instructions. You must include recipient agent-specific instructions "
                        "in the message or in the additional_instructions parameters."
                    ),
                },
                "message": {
                    "type": "string",
                    "description": (
                        "Specify the task required for the recipient agent to complete. Focus on clarifying "
                        "what the task entails, rather than providing exact instructions. Make sure to include "
                        "all the relevant information from the conversation needed to complete the task."
                    ),
                },
                "additional_instructions": {
                    "type": "string",
                    "description": (
                        "Optional. Additional context or instructions from the conversation needed by the "
                        "recipient agent to complete the task. If not needed, provide an empty string."
                    ),
                },
            },
            # OpenAI API requires all properties in 'required' array, even optional ones
            "required": ["recipient_agent", "my_primary_instructions", "message", "additional_instructions"],
            "additionalProperties": False,
        }

        # Allow subclasses to define extra params via Pydantic
        # Two supported patterns:
        # 1) Nested class `ExtraParams(BaseModel)` on the subclass
        # 2) Class attribute `extra_params_model = MyModel`
        self._extra_params_model: type[BaseModel] | None = None
        extra_model: Any = getattr(self.__class__, "ExtraParams", None) or getattr(
            self.__class__, "extra_params_model", None
        )
        try:
            if extra_model and isinstance(extra_model, type) and issubclass(extra_model, BaseModel):
                # Merge model schema into params schema
                model_schema: dict[str, Any] = extra_model.model_json_schema()  # type: ignore[assignment]
                # Only use field-level schema content
                model_properties: dict[str, Any] = model_schema.get("properties", {})
                model_required: list[str] = list(model_schema.get("required", []))

                # Apply properties and required
                if isinstance(model_properties, dict) and model_properties:
                    params_schema["properties"].update(model_properties)
                if isinstance(model_required, list) and model_required:
                    # Ensure unique while preserving order
                    existing_required: list[str] = list(params_schema.get("required", []))
                    for field_name in model_required:
                        if field_name not in existing_required:
                            existing_required.append(field_name)
                    params_schema["required"] = existing_required

                self._extra_params_model = extra_model
        except Exception as e:
            logger.warning(f"Failed to merge ExtraParams model into schema for '{name}': {e}")

        # Build description with all recipient roles
        description_parts = [self.__doc__ or "Send a message to another agent."]
        if recipient_names:
            description_parts.append("\n\nAvailable recipient agents:")
            for agent in recipient_names:
                agent_desc = getattr(agent, "description", "No description provided") or "No description provided"
                description_parts.append(f"\n- {agent.name}: {agent_desc}")
        final_description = "".join(description_parts)

        super().__init__(
            name=name,
            description=final_description,
            params_json_schema=params_schema,
            on_invoke_tool=self.on_invoke_tool,
        )
        logger.debug(
            f"Initialized SendMessage tool for sender '{sender_agent.name}' with {len(self.recipients)} recipient(s)"
        )

    def add_recipient(self, recipient_agent: "Agent") -> None:
        """
        Adds a new recipient agent to the tool and updates the schema.

        Args:
            recipient_agent: The agent to add as a recipient
        """
        # Store with lowercase key for case-insensitive lookup
        recipient_key = recipient_agent.name.lower()
        self.recipients[recipient_key] = recipient_agent

        # Update the schema with new recipient enum
        self._update_schema()

        logger.debug(
            f"Added recipient '{recipient_agent.name}' to SendMessage tool. Total recipients: {len(self.recipients)}"
        )

    def _update_schema(self) -> None:
        """Updates the tool schema with current recipients."""
        # Build the recipient agent enum values for the schema
        recipient_names = list(self.recipients.values())
        recipient_enum = [agent.name for agent in recipient_names] if recipient_names else []

        # Update the params schema
        self.params_json_schema["properties"]["recipient_agent"]["enum"] = recipient_enum

        # Update description with all recipient roles
        description_parts = [self.__doc__ or "Send a message to another agent."]
        if recipient_names:
            description_parts.append("\n\nAvailable recipient agents:")
            for agent in recipient_names:
                agent_desc = getattr(agent, "description", "No description provided") or "No description provided"
                description_parts.append(f"\n- {agent.name}: {agent_desc}")
        self.description = "".join(description_parts)

    def _create_recipient_agency_context(self, wrapper: RunContextWrapper[MasterContext]) -> "AgencyContext":
        """Create agency context for the recipient agent."""
        # Avoid circular import
        from ..agent.core import AgencyContext

        # Create a minimal agency context for multi-agent communication
        class MinimalAgency:
            def __init__(self, agents_dict, user_context):
                self.agents = agents_dict
                self.user_context = user_context

        # Since we're using send_message tool, we're always in an agency context
        agency_instance = MinimalAgency(wrapper.context.agents, wrapper.context.user_context)

        # Get shared instructions from the current context
        shared_instructions_from_context = wrapper.context.shared_instructions

        return AgencyContext(
            agency_instance=agency_instance,
            thread_manager=wrapper.context.thread_manager,
            subagents=self.recipients,
            load_threads_callback=None,
            save_threads_callback=None,
            shared_instructions=shared_instructions_from_context,
        )

    async def on_invoke_tool(self, wrapper: RunContextWrapper[MasterContext], arguments_json_string: str) -> str:
        """
        Handles the invocation of this specific send message tool.
        Retrieves the message from kwargs, validates context, calls the recipient agent's
        get_response method, and returns the text result.

        When the original request was made with get_response_stream, this will use
        get_response_stream for the sub-agent call to maintain streaming consistency.
        """
        # Get the tool_call_id from the wrapper (it's a ToolContext)
        # This is the call_id that OpenAI assigned to this send_message invocation
        tool_call_id = getattr(wrapper, "tool_call_id", None)
        if not tool_call_id:
            logger.warning(f"No tool_call_id found in wrapper. Type: {type(wrapper).__name__}")
            # Fallback to using agent's run_id if no tool_call_id available
            tool_call_id = (
                getattr(wrapper.context, "_current_agent_run_id", None) if wrapper and wrapper.context else None
            )

        try:
            kwargs = json.loads(arguments_json_string)
        except json.JSONDecodeError as e:
            logger.error(f"Tool '{self.name}' invoked with invalid JSON arguments: {arguments_json_string}. Error: {e}")
            return f"Error: Invalid arguments format for tool {self.name}. Expected a valid JSON string."

        recipient_agent_name = kwargs.get("recipient_agent")
        message_content = kwargs.get("message")
        my_primary_instructions = kwargs.get("my_primary_instructions")
        additional_instructions = kwargs.get("additional_instructions", "")

        # Validate extra params, if a Pydantic model was provided by subclass
        model_cls = getattr(self, "_extra_params_model", None)
        if model_cls is not None:
            try:
                # Only pass fields known to the model
                model_fields = set(model_cls.model_fields.keys())
                model_input = {k: v for k, v in kwargs.items() if k in model_fields}
                # Instantiate to trigger validation; we don't use the instance further here
                model_cls(**model_input)
            except ValidationError as e:
                logger.error(f"Invalid extra SendMessage parameters: {e}")
                return f"Error: Invalid extra parameters for tool {self.name}. Details: {e}"

        if not recipient_agent_name:
            logger.error(f"Tool '{self.name}' invoked without 'recipient_agent' parameter.")
            return f"Error: Missing required parameter 'recipient_agent' for tool {self.name}."
        if not message_content:
            logger.error(f"Tool '{self.name}' invoked without 'message' parameter.")
            return f"Error: Missing required parameter 'message' for tool {self.name}."
        if not my_primary_instructions:
            logger.error(f"Tool '{self.name}' invoked without 'my_primary_instructions' parameter.")
            return f"Error: Missing required parameter 'my_primary_instructions' for tool {self.name}."

        # Case-insensitive lookup for recipient agent
        recipient_key = recipient_agent_name.lower()
        if recipient_key not in self.recipients:
            logger.error(f"Tool '{self.name}' invoked with unknown recipient: '{recipient_agent_name}'")
            available = list(self.recipients.values())
            available_names = [a.name for a in available] if available else []
            return (
                f"Error: Unknown recipient agent '{recipient_agent_name}'. "
                f"Available agents: {', '.join(available_names)}"
            )

        # Thread-safe check and add for pending recipients
        async with self._pending_lock:
            # Check if this recipient already has a pending message
            if recipient_key in self._pending_recipients:
                logger.warning(
                    f"Attempted to send message to '{recipient_agent_name}' while previous message is still pending"
                )
                return (
                    f"Error: Cannot send another message to '{recipient_agent_name}' "
                    f"while the previous message is still being processed. "
                    f"Please wait for the agent to respond before sending another message."
                )

            # Mark this recipient as having a pending message
            self._pending_recipients.add(recipient_key)

        self.recipient_agent = self.recipients[recipient_key]
        sender_name_for_call = self.sender_agent.name
        recipient_name_for_call = self.recipient_agent.name

        logger.info(
            f"Agent '{sender_name_for_call}' invoking tool '{self.name}'. "
            f"Recipient: '{recipient_name_for_call}', "
            f'Message: "{str(message_content)[:50]}..."'
        )

        try:
            # Check if we should use streaming based on context
            # This is a simple heuristic: check if the wrapper has a streaming indicator
            use_streaming = False
            if wrapper and hasattr(wrapper, "context") and wrapper.context:
                # Check for streaming indicator in context
                use_streaming = getattr(wrapper.context, "_is_streaming", False)

            if use_streaming:
                logger.debug(
                    f"Calling target agent '{recipient_name_for_call}'.get_response_stream (streaming mode)..."
                )

                # Check if we have a streaming context to forward events
                streaming_context = None
                if wrapper and hasattr(wrapper, "context") and wrapper.context:
                    streaming_context = getattr(wrapper.context, "_streaming_context", None)

                # Use streaming and collect the final output
                final_output_text = ""
                tool_calls_seen = []

                # Create agency context for the recipient agent
                recipient_agency_context = self._create_recipient_agency_context(wrapper)

                async for event in self.recipient_agent.get_response_stream(
                    message=message_content,
                    sender_name=self.sender_agent.name,
                    additional_instructions=additional_instructions or None,
                    agency_context=recipient_agency_context,
                    parent_run_id=tool_call_id,  # Use tool_call_id as parent_run_id
                ):
                    # Non-destructively add agent/caller and attach IDs
                    event = add_agent_name_to_event(
                        event,
                        self.recipient_agent.name,
                        self.sender_agent.name,
                        agent_run_id=None,
                        parent_run_id=tool_call_id,
                    )

                    # Forward event to streaming context if available
                    if streaming_context:
                        try:
                            await streaming_context.put_event(event)
                        except Exception as e:
                            logger.warning(f"Failed to forward sub-agent event: {e}")

                    # Also process locally for the final output
                    if hasattr(event, "item") and event.item:
                        item = event.item

                        # Log tool calls from sub-agent
                        if hasattr(item, "type") and item.type == "tool_call_item":
                            if hasattr(item, "raw_item") and hasattr(item.raw_item, "name"):
                                tool_name = item.raw_item.name
                                tool_calls_seen.append(tool_name)
                                logger.info(f"[SUB-AGENT '{recipient_name_for_call}'] Tool call: {tool_name}")

                        # Extract final output
                        elif hasattr(item, "type") and item.type == "message_output_item":
                            if hasattr(item, "raw_item") and hasattr(item.raw_item, "content"):
                                content = item.raw_item.content
                                if content and len(content) > 0:
                                    text_content = getattr(content[0], "text", "")
                                    if text_content:
                                        final_output_text = text_content

                    # Send error message to the caller if it occurs
                    if isinstance(event, dict) and event.get("type") == "error":
                        final_output_text = (
                            f"Error getting response from the agent: {event.get('content', 'Unknown error')}"
                        )

                if tool_calls_seen:
                    logger.info(f"Sub-agent '{recipient_name_for_call}' executed tools: {tool_calls_seen}")

                logger.info(
                    f"Received response via tool '{self.name}' from '{recipient_name_for_call}': "
                    f'"{final_output_text[:50]}..."'
                )
                return final_output_text
            else:
                logger.debug(f"Calling target agent '{recipient_name_for_call}'.get_response...")

                # Create agency context for the recipient agent
                recipient_agency_context = self._create_recipient_agency_context(wrapper)

                response = await self.recipient_agent.get_response(
                    message=message_content,
                    sender_name=self.sender_agent.name,
                    additional_instructions=additional_instructions or None,
                    agency_context=recipient_agency_context,
                    parent_run_id=tool_call_id,  # Use tool_call_id as parent_run_id
                )

            current_final_output = response.final_output
            if current_final_output is None:
                final_output_text = ""  # Represent None as an empty string
            elif isinstance(current_final_output, str):
                final_output_text = current_final_output  # Use string (including empty string) as is
            else:
                # For any other type (bool, int, float, custom object), convert to string
                final_output_text = str(current_final_output)

            logger.info(
                f"Received response via tool '{self.name}' from '{recipient_name_for_call}': "
                f'"{final_output_text[:50]}..."'
            )
            return final_output_text

        except InputGuardrailTripwireTriggered as e:
            guidance = getattr(getattr(e, "guardrail_result", None), "output", None)
            message = getattr(guidance, "output_info", str(e)) if guidance else str(e)
            logger.warning(
                f"Input guardrail triggered during sub-call via tool '{self.name}' from "
                f"'{sender_name_for_call}' to '{recipient_name_for_call}': {message}"
            )
            if self.recipient_agent.throw_input_guardrail_error:
                return f"Error getting response from the agent: {message}"
            else:
                return message

        except Exception as e:
            logger.error(
                f"Error occurred during sub-call via tool '{self.name}' "
                f"from '{sender_name_for_call}' to '{recipient_name_for_call}': {e}",
                exc_info=True,
            )
            return f"Error: Failed to get response from agent '{recipient_name_for_call}'. Reason: {e}"
        finally:
            # Always remove the recipient from pending set when done (thread-safe)
            async with self._pending_lock:
                self._pending_recipients.discard(recipient_key)


class SendMessageHandoff:
    """
    A handoff configuration class for defining agent handoffs.
    """

    def create_handoff(self, recipient_agent: "Agent"):
        """Create and return the handoff object."""
        recipient_agent_name = recipient_agent.name
        handoff_object = handoff(
            agent=recipient_agent,
            tool_description_override=recipient_agent.description,
            tool_name_override=f"transfer_to_{recipient_agent_name.replace(' ', '_')}",
        )

        # Add a `recipient_agent` field to the input JSON schema to unify send message and handoff tool calls
        class InputArgs(BaseModel):
            recipient_agent: Literal[recipient_agent_name]  # type: ignore[valid-type]

        schema = strict_schema.ensure_strict_json_schema(InputArgs.model_json_schema())
        handoff_object.input_json_schema = schema
        return handoff_object
