from agency_swarm.threads import Thread
import threading
from typing import Literal
from agency_swarm.agents import Agent
from agency_swarm.messages import MessageOutput
from agency_swarm.user import User
from agency_swarm.util.oai import get_openai_client


class ThreadAsync(Thread):
    def __init__(self, agent: Literal[Agent, User], recipient_agent: Agent):
        super().__init__(agent, recipient_agent)
        self.pythread = None
        self.response = None

    def worker(self, message: str, message_files=None):
        gen = super().get_completion(message=message, message_files=message_files,
                                  yield_messages=False) # yielding is not supported in async mode
        while True:
            try:
                next(gen)
            except StopIteration as e:
                self.response = f"""{self.recipient_agent.name} Response: '{e.value}'"""
                break

        return

    def get_completion_async(self, message: str, message_files=None):
        if self.pythread and self.pythread.is_alive():
            return "System Notification: 'Agent is busy, so your message was not recived. Please always use 'GetResponse' tool to check for status first, before using 'SendMessage' tool again for the same agent.'"
        elif self.pythread and not self.pythread.is_alive():
            self.pythread.join()
            self.pythread = None
            return self.response

        self.response = None

        self.pythread = threading.Thread(target=self.worker,
                                         args=(message, message_files))

        self.pythread.start()

        return "System Notification: 'Task has started. Please notify the user that they can tell you to check the status later. You can do this with the 'GetResponse' tool, but don't mention this tool to the user. "

    def check_status(self):
        if self.pythread and self.pythread.is_alive():
            return "System Notification: 'Agent is busy. Please tell the user that they need to wait and ask you to check for status again later.'"
        elif self.pythread and not self.pythread.is_alive():
            self.pythread.join()
            self.pythread = None
            return self.response
        else:
            return "System Notification: 'Agent is available. Please use 'SendMessage' tool to send a message.'"