from abc import ABC, abstractmethod
from typing import Dict

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
            usage: Usage object containing token usage statistics
            assistant_id: ID of the assistant that generated the usage
            thread_id: ID of the thread that generated the usage
            model: Model that generated the usage
        """
        pass

    @abstractmethod
    def get_total_tokens(self) -> Dict[str, int]:
        """
        Get total token usage statistics.

        Returns:
            Dictionary containing total token usage statistics
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """
        Close the tracker. Called automatically when the tracker is garbage collected.
        """
        pass

    def __del__(self):
        self.close()

    @classmethod
    def get_observe_decorator(cls):
        """
        Get the observe decorator for the tracker. Will be applied to the get_completion function.

        Returns:
            The observe decorator
        """
        pass
