import threading
from typing import Literal, Optional, List

from openai.types.beta import AssistantToolChoice

from agency_swarm.agents import Agent
from agency_swarm.threads import Thread
from agency_swarm.user import User


class ThreadAsync(Thread):
    def __init__(self, agent: Literal[Agent, User], recipient_agent: Agent):
        super().__init__(agent, recipient_agent)
        self.pythread = None
        self.response = None

    def worker(self,
               message: str,
               message_files: List[str] = None,
               attachments: Optional[List[dict]] = None,
               recipient_agent=None,
               additional_instructions: str = None,
               tool_choice: AssistantToolChoice = None
               ):
        output = super().get_completion(message=message,
                                        message_files=message_files,
                                        attachments=attachments,
                                        recipient_agent=recipient_agent,
                                        additional_instructions=additional_instructions,
                                        tool_choice=tool_choice)

        self.response = f"""{self.recipient_agent.name}'s Response: '{output}'"""

        return

    def get_completion_async(self,
                             message: str,
                             message_files: List[str] = None,
                             attachments: Optional[List[dict]] = None,
                             recipient_agent=None,
                             additional_instructions: str = None,
                             tool_choice: AssistantToolChoice = None,
                             ):
        if self.pythread and self.pythread.is_alive():
            return "System Notification: 'Agent is busy, so your message was not received. Please always use 'GetResponse' tool to check for status first, before using 'SendMessage' tool again for the same agent.'"
        elif self.pythread and not self.pythread.is_alive():
            self.pythread.join()
            self.pythread = None
            self.response = None

        run = self.get_last_run()

        if run and run.status in ['queued', 'in_progress', 'requires_action']:
            return "System Notification: 'Agent is busy, so your message was not received. Please always use 'GetResponse' tool to check for status first, before using 'SendMessage' tool again for the same agent.'"

        self.pythread = threading.Thread(target=self.worker,
                                         args=(message, message_files, attachments, recipient_agent, additional_instructions, tool_choice))

        self.pythread.start()

        return "System Notification: 'Task has started. Please notify the user that they can tell you to check the status later. You can do this with the 'GetResponse' tool, after you have been instructed to do so. Don't mention the tool itself to the user. "

    def check_status(self, run=None):
        if not run:
            run = self.get_last_run()

        if not run:
            return "System Notification: 'Agent is ready to receive a message. Please send a message with the 'SendMessage' tool.'"

        # check run status
        if run.status in ['queued', 'in_progress', 'requires_action']:
            return "System Notification: 'Task is not completed yet. Please tell the user to wait and try again later.'"

        if run.status == "failed":
            return f"System Notification: 'Agent run failed with error: {run.last_error.message}. You may send another message with the 'SendMessage' tool.'"

        messages = self.client.beta.threads.messages.list(
            thread_id=self.id,
            order="desc",
        )

        return f"""{self.recipient_agent.name}'s Response: '{messages.data[0].content[0].text.value}'"""

    def get_last_run(self):
        if not self.thread:
            self.init_thread()

        runs = self.client.beta.threads.runs.list(
            thread_id=self.thread.id,
            order="desc",
        )

        if len(runs.data) == 0:
            return None

        run = runs.data[0]

        return run
