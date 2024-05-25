from abc import ABC

from openai.lib.streaming import AssistantEventHandler


class AgencyEventHandler(AssistantEventHandler, ABC):
    _agent_name = None
    _recipient_agent_name = None
    _agent = None
    _recipient_agent = None

    @classmethod
    def on_all_streams_end(cls):
        """Fires when streams for all agents have ended, as there can be multiple if you're agents are communicating
        with each other or using tools."""
        pass

    @classmethod
    @property
    def agent(cls):
        return cls._agent

    @agent.setter
    @classmethod
    def agent(cls, value):
        cls._agent = value
        cls._agent_name = value.name if value else None

    @classmethod
    @property
    def recipient_agent(cls):
        return cls._recipient_agent

    @recipient_agent.setter
    @classmethod
    def recipient_agent(cls, value):
        cls._recipient_agent = value
        cls._recipient_agent_name = value.name if value else None

    @classmethod
    @property
    def agent_name(cls):
        return cls._agent_name

    @classmethod
    @property
    def recipient_agent_name(cls):
        return cls._recipient_agent_name

