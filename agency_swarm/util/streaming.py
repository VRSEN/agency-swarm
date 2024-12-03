from abc import ABC
from typing import override

from openai.lib.streaming import AssistantEventHandler
from openai.types.beta.threads.runs.run_step import RunStep

from agency_swarm.util.usage_tracking.abstract_tracker import AbstractTracker


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
    usage_tracker: AbstractTracker

    @override
    def on_run_step_done(self, run_step: RunStep) -> None:
        """
        Handles the event when a run step is completed.
        """
        if run_step.usage and self.usage_tracker:
            self.usage_tracker.track_usage(run_step.usage)
