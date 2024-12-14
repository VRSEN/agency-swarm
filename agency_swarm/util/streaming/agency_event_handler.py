from abc import ABC

from openai.lib.streaming import AssistantEventHandler
from openai.types.beta.threads.runs.run_step import RunStep
from typing_extensions import override

from agency_swarm.util.constants import DEFAULT_MODEL
from agency_swarm.util.oai import get_tracker


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


class AgencyEventHandlerWithTracking(AgencyEventHandler):
    """
    A special event handler that implements tracking of usage for the run step.
    """

    @override
    @classmethod
    def on_run_step_done(cls, run_step: RunStep) -> None:
        """
        Implements tracking of usage for the run step.
        """
        if run_step.usage:
            tracker = get_tracker()
            model = (
                getattr(cls.agent, "model", None)
                or getattr(cls.recipient_agent, "model", None)
                or DEFAULT_MODEL
            )
            tracker.track_usage(
                usage=run_step.usage,
                assistant_id=run_step.assistant_id,
                thread_id=run_step.thread_id,
                sender_agent_name=cls.agent_name,
                recipient_agent_name=cls.recipient_agent_name,
                model=model,
            )
