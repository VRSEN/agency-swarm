from typing import ClassVar, Type
from agency_swarm.threads.thread_async import ThreadAsync
from .SendMessage import SendMessage

class SendMessageAsyncThreading(SendMessage):
    """Use this tool for asynchronous communication with other agents within your agency. Initiate tasks by messaging, and check status and responses later with the 'GetResponse' tool. Relay responses to the user, who instructs on status checks. Continue until task completion."""
    class ToolConfig:
        async_mode = "threading"