"""
Defines the SendMessage tool used for direct communication between agents.

This module provides the `SendMessage` class, a specialized `FunctionTool` that
allows one agent to send a message to another registered agent within the
Agency Swarm framework. The tool is dynamically configured with sender and
recipient details.
"""

import logging
from typing import TYPE_CHECKING

from agents import FunctionTool, RunContextWrapper, RunResult

from ..context import MasterContext

if TYPE_CHECKING:
    from ..agent import Agent

logger = logging.getLogger(__name__)

# Constant for the message parameter name
MESSAGE_PARAM = "message"


class SendMessage(FunctionTool):
    """
    A dynamically created tool for an agent to send a message to a specific registered recipient agent.

    This tool is instantiated by an agent to enable direct communication with another
    specific agent. It leverages the `FunctionTool` infrastructure and is configured
    at runtime with the sender, recipient, and a dynamically generated name and
    description to reflect the communication channel.
    """

    # Store references to the sender and recipient agents
    sender_agent: "Agent"
    recipient_agent: "Agent"

    def __init__(
        self,
        sender_agent: "Agent",
        recipient_agent: "Agent",
        tool_name: str,
        tool_description: str,
    ):
        """
        Initializes the specific send message tool.

        Args:
            sender_agent: The agent instance that owns this tool.
            recipient_agent: The agent instance that this tool communicates with.
            tool_name: The specific name for this tool (e.g., "send_message_to_RecipientAgent").
            tool_description: The description for this tool, including context about the recipient.
        """
        self.sender_agent = sender_agent
        self.recipient_agent = recipient_agent

        # Define the JSON schema for the 'message' parameter
        params_schema = {
            "type": "object",
            "properties": {
                MESSAGE_PARAM: {
                    "type": "string",
                    "description": f"The message content to send to the {recipient_agent.name}.",
                },
            },
            "required": [MESSAGE_PARAM],
            "additionalProperties": False,  # Enforce only the defined parameter
        }

        # Initialize the FunctionTool base class
        super().__init__(
            name=tool_name,
            description=tool_description,
            params_json_schema=params_schema,
            on_invoke_tool=self.on_invoke_tool,
        )
        logger.debug(
            f"Initialized SendMessage tool: '{self.name}' for sender '{sender_agent.name}' -> recipient '{recipient_agent.name}'"
        )

    async def on_invoke_tool(self, wrapper: RunContextWrapper[MasterContext], **kwargs: str) -> str:
        """
        Handles the invocation of this specific send message tool.

        Retrieves the message from kwargs, validates context, calls the recipient agent's
        get_response method, and returns the text result.

        Args:
            wrapper: The run context wrapper.
            **kwargs: Must contain the 'message' parameter.

        Returns:
            A string containing the response from the recipient agent.
        """
        master_context: MasterContext = wrapper.context
        message_content = kwargs.get(MESSAGE_PARAM)

        if not message_content:
            logger.error(f"Tool '{self.name}' invoked without '{MESSAGE_PARAM}' parameter.")
            # Return an error string
            return f"Error: Missing required parameter '{MESSAGE_PARAM}' for tool {self.name}."

        # Get chat_id from context
        current_chat_id = master_context.chat_id
        if not current_chat_id:
            # This should ideally not happen if context is prepared correctly
            logger.error(f"Tool '{self.name}' invoked without 'chat_id' in MasterContext.")
            # Return an error string
            return "Error: Internal context error. Missing chat_id for agent communication."

        sender_name = self.sender_agent.name
        recipient_name = self.recipient_agent.name

        logger.info(
            f"Agent '{sender_name}' invoking tool '{self.name}'. "
            f"Recipient: '{recipient_name}', ChatID: {current_chat_id}, "
            f'Message: "{message_content[:50]}..."'
        )

        try:
            # Call the recipient agent's get_response method directly
            logger.debug(f"Calling target agent '{recipient_name}'.get_response...")

            # --- IMPORTANT ---
            # Pass the current chat_id and sender_name.
            # Pass only the user_context part of the master context as context_override.
            # The Runner within the recipient's get_response will handle history, hooks, etc.
            sub_run_result: RunResult = await self.recipient_agent.get_response(
                message=message_content,
                sender_name=sender_name,
                chat_id=current_chat_id,
                context_override=master_context.user_context,  # Pass only user context
                # Do NOT pass hooks or run_config from here.
            )

            # Extract the final text output for the tool result
            final_output_text = sub_run_result.final_output or "(No text output from recipient)"
            logger.info(
                f"Received response via tool '{self.name}' from '{recipient_name}': \"{final_output_text[:50]}...\""
            )

            # The tool itself returns the raw output text
            # The Runner will handle adding this as a ToolCallOutputItem
            return final_output_text

        except Exception as e:
            logger.error(
                f"Error occurred during sub-call via tool '{self.name}' from '{sender_name}' to '{recipient_name}': {e}",
                exc_info=True,
            )
            # Return an error string
            return f"Error: Failed to get response from agent '{recipient_name}'. Reason: {e}"


# --- Remove the old generic tool export ---
SEND_MESSAGE_TOOL_NAME = None
send_message_tool = None
