from abc import ABC, abstractmethod
from typing import Any

from openai.types.beta.threads.runs.run_step import Usage


class AbstractTracker(ABC):
    """
    Abstract interface for usage tracking implementations.
    """

    @abstractmethod
    def track_assistant_message(
        self, client: Any, thread_id: str, run_id: str, message_content: str
    ):
        """
        Track an assistant message with detailed context.

        Args:
            client: The OpenAI client instance
            thread_id (str): ID of the thread
            run_id (str): ID of the run
            message_content (str): The content of the assistant's message
        """
        pass

    @abstractmethod
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
        Track token usage.

        Args:
            usage (Usage): Object containing token usage statistics.
            assistant_id (str): ID of the assistant that generated the usage.
            thread_id (str): ID of the thread that generated the usage.
            model (str): Model that generated the usage.
            sender_agent_name (str): Name of the sender agent.
            recipient_agent_name (str): Name of the recipient agent.
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

    @classmethod
    @abstractmethod
    def get_observe_decorator(cls):
        """
        Get the observe decorator for the tracker. Will be applied to the get_completion function.

        Returns:
            Callable: The observe decorator.
        """
        pass
