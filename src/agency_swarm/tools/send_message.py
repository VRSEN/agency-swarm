"""
Defines the SendMessage and SendMessageHandoff tools for direct communication between agents.

This module provides the `SendMessage` class, a specialized `FunctionTool` that
allows one agent to send a message to another registered agent within the
Agency Swarm framework. The tool is dynamically configured with sender and
recipient details.
"""

import json
import logging
from typing import TYPE_CHECKING

from agents import FunctionTool, RunContextWrapper, handoff

from ..context import MasterContext
from ..messages.message_formatter import MessageFormatter
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

    def __init__(
        self,
        sender_agent: "Agent",
        recipients: dict[str, "Agent"] | None = None,
        name: str = "send_message",
    ):
        self.sender_agent = sender_agent
        self.recipients = recipients or {}

        # Build the recipient agent enum values for the schema
        recipient_names = list(self.recipients.values())
        recipient_enum = [agent.name for agent in recipient_names] if recipient_names else []

        # Rich parameter schema incorporating all field descriptions
        params_schema = {
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
            "required": ["recipient_agent", "my_primary_instructions", "message", "additional_instructions"],
            "additionalProperties": False,
        }

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

    def _combine_instructions(self, shared_instructions: str | None, additional_instructions: str | None) -> str | None:
        """Combine shared instructions with additional instructions."""
        if not shared_instructions and not additional_instructions:
            return None

        parts = []
        if shared_instructions:
            parts.append(shared_instructions)
        if additional_instructions:
            parts.append(additional_instructions)

        return "\n\n---\n\n".join(parts) if parts else None

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

                # Combine shared instructions with any additional instructions for agent-to-agent communication
                combined_instructions = self._combine_instructions(
                    recipient_agency_context.shared_instructions, additional_instructions
                )

                async for event in self.recipient_agent.get_response_stream(
                    message=message_content,
                    sender_name=self.sender_agent.name,
                    additional_instructions=combined_instructions,
                    agency_context=recipient_agency_context,
                    parent_run_id=tool_call_id,  # Use tool_call_id as parent_run_id
                ):
                    # Add agent name and caller to the event before forwarding
                    event = add_agent_name_to_event(event, self.recipient_agent.name, self.sender_agent.name)

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

                if tool_calls_seen:
                    logger.info(f"Sub-agent '{recipient_name_for_call}' executed tools: {tool_calls_seen}")

                response = type("StreamedResponse", (), {"final_output": final_output_text})()
            else:
                logger.debug(f"Calling target agent '{recipient_name_for_call}'.get_response...")

                # Create agency context for the recipient agent
                recipient_agency_context = self._create_recipient_agency_context(wrapper)

                # Combine shared instructions with any additional instructions for agent-to-agent communication
                combined_instructions = self._combine_instructions(
                    recipient_agency_context.shared_instructions, additional_instructions
                )

                response = await self.recipient_agent.get_response(
                    message=message_content,
                    sender_name=self.sender_agent.name,
                    additional_instructions=combined_instructions,
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

        except Exception as e:
            logger.error(
                f"Error occurred during sub-call via tool '{self.name}' "
                f"from '{sender_name_for_call}' to '{recipient_name_for_call}': {e}",
                exc_info=True,
            )
            return f"Error: Failed to get response from agent '{recipient_name_for_call}'. Reason: {e}"


class SendMessageHandoff:
    """
    A handoff configuration class for defining agent handoffs.
    """

    def create_handoff(self, recipient_agent: "Agent"):
        """Create and return the handoff object."""
        # Check if recipient agent uses litellm
        if MessageFormatter._is_litellm_model(recipient_agent):
            # Create input filter to adjust history for litellm
            def litellm_input_filter(handoff_data):
                # Extract the conversation history
                input_history = handoff_data.input_history

                # Convert to list if it's a tuple
                if isinstance(input_history, tuple):
                    history_list = list(input_history)
                elif isinstance(input_history, str):
                    # If it's a string, we can't adjust it easily
                    return handoff_data
                else:
                    history_list = input_history

                # Apply litellm adjustments
                adjusted_history = MessageFormatter.adjust_history_for_litellm(history_list)

                # Create new handoff data with adjusted history
                from dataclasses import replace

                return replace(handoff_data, input_history=tuple(adjusted_history))

            # Create handoff with litellm input filter
            return handoff(
                agent=recipient_agent,
                tool_description_override=recipient_agent.description,
                input_filter=litellm_input_filter,
            )
        else:
            # Standard handoff for non-litellm agents
            return handoff(
                agent=recipient_agent,
                tool_description_override=recipient_agent.description,
            )
