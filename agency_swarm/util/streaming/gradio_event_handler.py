import queue
from typing import Type

from openai.types.beta.threads import Message
from openai.types.beta.threads.runs.run_step import RunStep
from openai.types.beta.threads.runs.tool_call import (
    CodeInterpreterToolCall,
    FileSearchToolCall,
    FunctionToolCall,
    ToolCall,
)
from typing_extensions import override

from agency_swarm.messages import MessageOutput
from agency_swarm.util.streaming import AgencyEventHandler


def create_gradio_handler(chatbot_queue: queue.Queue) -> Type[AgencyEventHandler]:
    """
    Factory function that creates a new GradioEventHandler class with proper dependencies.
    This ensures thread safety by creating a new class with its own class-level attributes.

    Args:
        chatbot_queue: The chatbot queue to be associated with the handler

    Returns:
        Type[GradioEventHandler]: A new GradioEventHandler class with proper dependencies
    """

    class GradioHandler(AgencyEventHandler):
        _chatbot_queue = chatbot_queue
        _message_output = None

        @classmethod
        def change_recipient_agent(cls, recipient_agent_name):
            cls._chatbot_queue.put("[change_recipient_agent]")
            cls._chatbot_queue.put(recipient_agent_name)

        @override
        def on_message_created(self, message: Message) -> None:
            if message.role == "user":
                full_content = ""
                for content in message.content:
                    if content.type == "image_file":
                        full_content += f"🖼️ Image File: {content.image_file.file_id}\n"
                        continue

                    if content.type == "image_url":
                        full_content += f"\n{content.image_url.url}\n"
                        continue

                    if content.type == "text":
                        full_content += content.text.value + "\n"

                self._message_output = MessageOutput(
                    "text",
                    self.agent_name,
                    self.recipient_agent_name,
                    full_content,
                )

            else:
                self._message_output = MessageOutput(
                    "text", self.recipient_agent_name, self.agent_name, ""
                )

            self._chatbot_queue.put("[new_message]")
            self._chatbot_queue.put(self._message_output.get_formatted_content())

        @override
        def on_text_delta(self, delta, snapshot):
            self._chatbot_queue.put(delta.value)

        @override
        def on_tool_call_created(self, tool_call: ToolCall):
            if isinstance(tool_call, dict):
                if "type" not in tool_call:
                    tool_call["type"] = "function"

                if tool_call["type"] == "function":
                    tool_call = FunctionToolCall(**tool_call)
                elif tool_call["type"] == "code_interpreter":
                    tool_call = CodeInterpreterToolCall(**tool_call)
                elif (
                    tool_call["type"] == "file_search"
                    or tool_call["type"] == "retrieval"
                ):
                    tool_call = FileSearchToolCall(**tool_call)
                else:
                    raise ValueError("Invalid tool call type: " + tool_call["type"])

            # TODO: add support for code interpreter and retrieval tools
            if tool_call.type == "function":
                self._chatbot_queue.put("[new_message]")
                self._message_output = MessageOutput(
                    "function",
                    self.recipient_agent_name,
                    self.agent_name,
                    str(tool_call.function),
                )
                self._chatbot_queue.put(
                    self._message_output.get_formatted_header() + "\n"
                )

        @override
        def on_tool_call_done(self, snapshot: ToolCall):
            if isinstance(snapshot, dict):
                if "type" not in snapshot:
                    snapshot["type"] = "function"

                if snapshot["type"] == "function":
                    snapshot = FunctionToolCall(**snapshot)
                elif snapshot["type"] == "code_interpreter":
                    snapshot = CodeInterpreterToolCall(**snapshot)
                elif snapshot["type"] == "file_search":
                    snapshot = FileSearchToolCall(**snapshot)
                else:
                    raise ValueError("Invalid tool call type: " + snapshot["type"])

            self._message_output = None

            # TODO: add support for code interpreter and retrieval tools
            if snapshot.type != "function":
                return

            self._chatbot_queue.put(str(snapshot.function))

            if snapshot.function.name == "SendMessage":
                try:
                    args = eval(snapshot.function.arguments)
                    recipient = args["recipient"]
                    self._message_output = MessageOutput(
                        "text",
                        self.recipient_agent_name,
                        recipient,
                        args["message"],
                    )

                    self._chatbot_queue.put("[new_message]")
                    self._chatbot_queue.put(
                        self._message_output.get_formatted_content()
                    )
                except Exception as e:
                    pass

            self._message_output = None

        @override
        def on_run_step_done(self, run_step: RunStep) -> None:
            super().on_run_step_done(run_step)

            if run_step.type == "tool_calls":
                for tool_call in run_step.step_details.tool_calls:
                    if tool_call.type != "function":
                        continue

                    if tool_call.function.name == "SendMessage":
                        continue

                    self._message_output = None
                    self._chatbot_queue.put("[new_message]")

                    self._message_output = MessageOutput(
                        "function_output",
                        tool_call.function.name,
                        self.recipient_agent_name,
                        tool_call.function.output,
                    )

                    self._chatbot_queue.put(
                        self._message_output.get_formatted_header() + "\n"
                    )
                    self._chatbot_queue.put(tool_call.function.output)

        @override
        @classmethod
        def on_all_streams_end(cls):
            cls._message_output = None
            cls._chatbot_queue.put("[end]")

    return GradioHandler
