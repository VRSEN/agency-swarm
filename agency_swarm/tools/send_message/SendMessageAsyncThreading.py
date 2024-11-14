from typing import ClassVar, Type
from agency_swarm.threads.thread_async import ThreadAsync
from .SendMessage import SendMessage

class SendMessageAsyncThreading(SendMessage):
    """Use this tool for asynchronous communication with other agents within your agency. Initiate tasks by messaging, and check status and responses later with the 'GetResponse' tool. Relay responses to the user, who instructs on status checks. Continue until task completion."""
    _thread_type: ClassVar[Type[ThreadAsync]] = ThreadAsync
    
    def run(self):
        thread: ThreadAsync = self._agents_and_threads[self._caller_agent.name][self.recipient.value]

        message = thread.get_completion_async(message=self.message,
                                                message_files=self.message_files,
                                                additional_instructions=self.additional_instructions)

        return message or ""