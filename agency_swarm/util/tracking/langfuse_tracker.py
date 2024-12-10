from typing import Any

from langfuse import Langfuse
from langfuse.decorators import langfuse_context, observe
from openai.types.beta.threads.runs.run_step import Usage

from agency_swarm.util.tracking.abstract_tracker import AbstractTracker


class LangfuseTracker(AbstractTracker):
    def __init__(self):
        self.client = Langfuse()

    @observe
    def track_assistant_message(
        self, client: Any, thread_id: str, run_id: str, message_content: str
    ):
        """
        Track an assistant message with detailed context using langfuse.
        """
        if not langfuse_context.client_instance:
            return

        # Get all messages for input context
        message_log = client.beta.threads.messages.list(thread_id=thread_id)
        input_messages = [
            {"role": msg.role, "content": msg.content[0].text.value}
            for msg in message_log.data[:-1]
        ]  # Exclude the last message (assistant's response)

        # Get run for token counts
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)

        # Log to langfuse
        langfuse_context.client_instance.generation(
            trace_id=langfuse_context.get_current_trace_id(),
            parent_observation_id=langfuse_context.get_current_observation_id(),
            model=run.model,
            usage=run.usage,
            input=input_messages,
            output=message_content,
        )

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
            trace_id=langfuse_context.get_current_trace_id(),
            parent_observation_id=langfuse_context.get_current_observation_id(),
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
