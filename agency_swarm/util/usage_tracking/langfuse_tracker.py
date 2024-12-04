from langfuse import Langfuse
from langfuse.decorators import observe
from openai.types.beta.threads.runs.run_step import Usage

from agency_swarm.util.usage_tracking.abstract_tracker import AbstractTracker


class LangfuseUsageTracker(AbstractTracker):
    def track_usage(
        self, usage: Usage, assistant_id: str, thread_id: str, model: str
    ) -> None:
        langfuse = Langfuse()
        langfuse.generation(
            model=model,
            metadata={
                "assistant_id": assistant_id,
                "thread_id": thread_id,
            },
            usage={
                "input": usage.prompt_tokens,
                "output": usage.completion_tokens,
                "total": usage.total_tokens,
                "unit": "TOKENS",
            },
        )

    def get_total_tokens(self) -> Usage:
        # TODO: Implement this
        return Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)

    def close(self) -> None:
        pass

    @classmethod
    def get_observe_decorator(cls):
        return observe
