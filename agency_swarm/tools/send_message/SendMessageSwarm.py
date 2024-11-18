from openai import BadRequestError
from agency_swarm.threads.thread import Thread
from .SendMessage import SendMessageBase

class SendMessageSwarm(SendMessageBase):
    """Use this tool to route messages to other agents within your agency. After using this tool, you will be switched to the recipient agent. This tool can only be used once per message. Do not use any other tools together with this tool."""

    class ToolConfig:
        # set output as result because the communication will be finished after this tool is called
        output_as_result: bool = True
        one_call_at_a_time: bool = True
    
    def run(self):            
        # get main thread
        thread = self._get_main_thread()

        # get recipient agent from thread
        recipient_agent = self._get_recipient_agent()

        # submit tool output
        try:
            thread._submit_tool_outputs(
                tool_outputs=[{"tool_call_id": self._tool_call.id, "output": "The request has been routed. You are now a " + recipient_agent.name + " agent. Please assist the user further with their request."}],
                poll=False
            )
        except BadRequestError as e:
            raise Exception("You can only call this tool by itself. Do not use any other tools together with this tool.")
        
        try:
            # cancel run
            thread._cancel_run()

            # change recipient agent in thread
            thread.recipient_agent = recipient_agent

            # change recipient agent in gradio dropdown
            if self._event_handler:
                if hasattr(self._event_handler, "change_recipient_agent"):
                    self._event_handler.change_recipient_agent(self.recipient.value)
            
            # continue conversation with the new recipient agent
            message = thread.get_completion(message=None, recipient_agent=recipient_agent, yield_messages=not self._event_handler, event_handler=self._event_handler)

            return message or ""
        except Exception as e:
            # we need to catch errors beucase tool outputs are already submitted
            print("Error in SendMessageSwarm: ", e)
            return str(e)
