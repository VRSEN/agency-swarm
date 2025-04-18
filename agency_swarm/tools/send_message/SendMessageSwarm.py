import logging
from typing import Generator, Union

from openai import BadRequestError

from agency_swarm.messages.message_output import MessageOutput

from .SendMessage import SendMessageBase


class SendMessageSwarm(SendMessageBase):
    """Use this tool to route messages to other agents within your agency. After using this tool, you will be switched to the recipient agent. This tool can only be used once per message. Do not use any other tools together with this tool."""

    class ToolConfig:
        # set output as result because the communication will be finished after this tool is called
        output_as_result: bool = True
        one_call_at_a_time: bool = True

    def run(self) -> Union[str, Generator[MessageOutput, None, None]]:
        logging.debug("SendMessageSwarm.run: Starting execution")

        # get main thread
        thread = self._get_main_thread()
        logging.debug(f"SendMessageSwarm.run: Got main thread: {thread}")

        # get recipient agent
        recipient_agent = self._get_recipient_agent()
        logging.debug(
            f"SendMessageSwarm.run: Got recipient agent: {recipient_agent.name}"
        )

        # submit tool output
        try:
            logging.debug("SendMessageSwarm.run: Submitting tool output")
            thread.submit_tool_outputs(
                tool_outputs=[
                    {
                        "tool_call_id": self._tool_call.id,
                        "output": "The request has been routed. You are now a "
                        + recipient_agent.name
                        + " agent. Please assist the user further with their request.",
                    }
                ],
                poll=False,
            )
            logging.debug("SendMessageSwarm.run: Tool output submitted successfully")
        except BadRequestError as e:
            logging.error(
                f"SendMessageSwarm.run: BadRequestError while submitting tool output: {e}"
            )
            raise Exception(
                "You can only call this tool by itself. Do not use any other tools together with this tool."
            )

        try:
            # cancel run
            logging.debug("SendMessageSwarm.run: Canceling current run")
            thread.cancel_run()
            logging.debug("SendMessageSwarm.run: Run canceled successfully")

            # change recipient agent in thread
            logging.debug(
                f"SendMessageSwarm.run: Changing recipient agent to {recipient_agent.name}"
            )
            thread.recipient_agent = recipient_agent

            # change recipient agent in gradio dropdown
            if self._event_handler:
                logging.debug("SendMessageSwarm.run: Updating event handler")
                if hasattr(self._event_handler, "change_recipient_agent"):
                    self._event_handler.change_recipient_agent(self.recipient.value)
                    logging.debug("SendMessageSwarm.run: Event handler updated")

            # continue conversation with the new recipient agent
            logging.debug(
                "SendMessageSwarm.run: Getting completion from new recipient agent"
            )
            message = thread.get_completion(
                message=None,
                recipient_agent=recipient_agent,
                event_handler=self._event_handler,
                yield_messages=not self._event_handler,
                parent_run_id=self._tool_call.id,
            )

            # Log only if message is a string (not a generator)
            if isinstance(message, str):
                logging.debug(
                    f"SendMessageSwarm.run: Got completion response: {message[:100]}..."
                )

            return message or ""
        except Exception as e:
            # we need to catch errors because tool outputs are already submitted
            logging.error(f"SendMessageSwarm.run: Error during execution: {e}")
            print("Error in SendMessageSwarm: ", e)
            return str(e)
