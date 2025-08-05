"""
Defines the SendMessage tool used for direct communication between agents.

This module provides the `SendMessage` class, a specialized `FunctionTool` that
allows one agent to send a message to another registered agent within the
Agency Swarm framework. The tool is dynamically configured with sender and
recipient details.
"""

import json
import logging
from typing import TYPE_CHECKING

from agents import FunctionTool, RunContextWrapper

from ..context import MasterContext

if TYPE_CHECKING:
    from ..agent_core import Agent

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
    recipient_agent: "Agent"

    def __init__(
        self,
        sender_agent: "Agent",
        recipient_agent: "Agent",
        tool_name: str,
    ):
        self.sender_agent = sender_agent
        self.recipient_agent = recipient_agent

        # Rich parameter schema incorporating all field descriptions
        params_schema = {
            "type": "object",
            "properties": {
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
            "required": ["my_primary_instructions", "message", "additional_instructions"],
            "additionalProperties": False,
        }

        # Combine own rich docstring with the recipient-specific description part
        recipient_role_description = (
            getattr(self.recipient_agent, "description", "No description provided") or "No description provided"
        )
        final_description = f"{self.__doc__}\n\nThis agent's role is: {recipient_role_description}"

        super().__init__(
            name=tool_name,
            description=final_description,
            params_json_schema=params_schema,
            on_invoke_tool=self.on_invoke_tool,
        )
        logger.debug(
            f"Initialized SendMessage tool: '{self.name}' "
            f"for sender '{sender_agent.name}' -> recipient '{recipient_agent.name}'"
        )

    async def on_invoke_tool(self, wrapper: RunContextWrapper[MasterContext], arguments_json_string: str) -> str:
        """
        Handles the invocation of this specific send message tool.
        Retrieves the message from kwargs, validates context, calls the recipient agent's
        get_response method, and returns the text result.

        When the original request was made with get_response_stream, this will use
        get_response_stream for the sub-agent call to maintain streaming consistency.
        """
        try:
            kwargs = json.loads(arguments_json_string)
        except json.JSONDecodeError as e:
            logger.error(f"Tool '{self.name}' invoked with invalid JSON arguments: {arguments_json_string}. Error: {e}")
            return f"Error: Invalid arguments format for tool {self.name}. Expected a valid JSON string."

        message_content = kwargs.get("message")
        my_primary_instructions = kwargs.get("my_primary_instructions")
        additional_instructions = kwargs.get("additional_instructions", "")

        if not message_content:
            logger.error(f"Tool '{self.name}' invoked without 'message' parameter.")
            return f"Error: Missing required parameter 'message' for tool {self.name}."
        if not my_primary_instructions:
            logger.error(f"Tool '{self.name}' invoked without 'my_primary_instructions' parameter.")
            return f"Error: Missing required parameter 'my_primary_instructions' for tool {self.name}."

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

                async for event in self.recipient_agent.get_response_stream(
                    message=message_content,
                    sender_name=self.sender_agent.name,
                    additional_instructions=additional_instructions,
                ):
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
                response = await self.recipient_agent.get_response(
                    message=message_content,
                    sender_name=self.sender_agent.name,
                    additional_instructions=additional_instructions,
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
