from langfuse import Langfuse
from langfuse.decorators import observe
from openai.types.beta.threads.runs.run_step import Usage

from agency_swarm.util.tracking.abstract_tracker import AbstractTracker


class LangfuseTracker(AbstractTracker):
    def __init__(self):
        self.client = Langfuse()

    def track_usage(
        self,
        usage: Usage,
        assistant_id: str,
        thread_id: str,
        model: str,
        sender_agent_name: str,
        recipient_agent_name: str,
    ) -> None:
        """
        Track usage by recording a generation event in Langfuse.
        """
        self.client.generation(
            model=model,
            metadata={
                "assistant_id": assistant_id,
                "thread_id": thread_id,
                "sender_agent_name": sender_agent_name,
                "recipient_agent_name": recipient_agent_name,
            },
            usage={
                "input": usage.prompt_tokens,
                "output": usage.completion_tokens,
                "total": usage.total_tokens,
                "unit": "TOKENS",
            },
        )

    def get_total_tokens(self) -> Usage:
        """
        Retrieve total usage from Langfuse by summing over all recorded generations.
        """
        generations = self.client.fetch_observations(type="GENERATION").data

        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0

        for generation in generations:
            if generation.usage:
                prompt_tokens += generation.usage.input or 0
                completion_tokens += generation.usage.output or 0
                total_tokens += generation.usage.total or 0

        return Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    @classmethod
    def get_observe_decorator(cls):
        return observe
