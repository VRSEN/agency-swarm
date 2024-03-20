from abc import ABC

from openai.lib.streaming import AssistantEventHandler


class AgencyEventHandler(AssistantEventHandler, ABC):
    agent_name = None
    recipient_agent_name = None

    @classmethod
    def on_all_streams_end(cls):
        """Fires when streams for all agents have ended, as there can be multiple if you're agents are communicating
        with each other or using tools."""
        pass
