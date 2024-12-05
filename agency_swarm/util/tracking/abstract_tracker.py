from abc import ABC, abstractmethod

from openai.types.beta.threads.runs.run_step import Usage


class AbstractTracker(ABC):
    """
    Abstract interface for usage tracking implementations.
    """

    @abstractmethod
    def track_usage(
        self, usage: Usage, assistant_id: str, thread_id: str, model: str
    ) -> None:
        """
        Track token usage.

        Args:
            usage (Usage): Object containing token usage statistics.
            assistant_id (str): ID of the assistant that generated the usage.
            thread_id (str): ID of the thread that generated the usage.
            model (str): Model that generated the usage.
        """
        pass

    @abstractmethod
    def get_total_tokens(self) -> Usage:
        """
        Get total token usage statistics accumulated so far.

        Returns:
            Usage: An object containing cumulative prompt, completion, and total tokens.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close the tracker and release resources, if any.
        """
        pass

    @classmethod
    @abstractmethod
    def get_observe_decorator(cls):
        """
        Get the observe decorator for the tracker. Will be applied to the get_completion function.

        Returns:
            Callable: The observe decorator.
        """
        pass
