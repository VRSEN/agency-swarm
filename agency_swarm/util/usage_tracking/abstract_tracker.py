from abc import ABC, abstractmethod
from typing import Dict

from openai.types.beta.threads.runs.run_step import Usage


class AbstractTracker(ABC):
    """
    Abstract interface for usage tracking implementations.
    """

    @abstractmethod
    def track_usage(self, usage: Usage) -> None:
        """
        Track token usage.

        Args:
            usage: Usage object containing token usage statistics
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
        Close the tracker.
        """
        pass
