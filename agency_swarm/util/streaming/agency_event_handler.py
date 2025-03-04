from abc import ABC

from openai.lib.streaming import AssistantEventHandler


class AgencyEventHandler(AssistantEventHandler, ABC):
    agent_name = None
    recipient_agent_name = None
    agent = None
    recipient_agent = None

    @classmethod
    def on_all_streams_end(cls):
        """Fires when streams for all agents have ended, as there can be multiple if you're agents are communicating
        with each other or using tools."""
        pass

    @classmethod
    def set_agent(cls, value):
        cls.agent = value
        cls.agent_name = value.name if value else None

    @classmethod
    def set_recipient_agent(cls, value):
        cls.recipient_agent = value
        cls.recipient_agent_name = value.name if value else None
