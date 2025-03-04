from typing import Type

from openai.types.beta.threads import Message
from openai.types.beta.threads.runs import RunStep
from openai.types.beta.threads.runs.tool_call import (
    CodeInterpreterToolCall,
    FileSearchToolCall,
    FunctionToolCall,
)
from typing_extensions import override

from agency_swarm.messages.message_output import MessageOutputLive
from agency_swarm.util.streaming.agency_event_handler import AgencyEventHandler


def create_term_handler(agency=None) -> Type[AgencyEventHandler]:
    """
    Factory function that creates a new TermEventHandler class with proper dependencies.
    This ensures thread safety by creating a new class with its own class-level attributes.

    Args:
        agency: The agency instance to be associated with the handler

    Returns:
        Type[TermEventHandler]: A new TermEventHandler class with proper dependencies
    """

    class TermEventHandler(AgencyEventHandler):
        _message_output = None
        _agency = agency

        @override
        def on_message_created(self, message: Message) -> None:
            if message.role == "user":
                self._message_output = MessageOutputLive(
                    "text", self.agent_name, self.recipient_agent_name, ""
                )
                self._message_output.cprint_update(message.content[0].text.value)
            else:
                self._message_output = MessageOutputLive(
                    "text", self.recipient_agent_name, self.agent_name, ""
                )

        @override
        def on_message_done(self, message: Message) -> None:
            self._message_output = None

        @override
        def on_text_delta(self, delta, snapshot):
            self._message_output.cprint_update(snapshot.value)

        @override
        def on_tool_call_created(self, tool_call):
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
                self._message_output = MessageOutputLive(
                    "function",
                    self.recipient_agent_name,
                    self.agent_name,
                    str(tool_call.function),
                )

        @override
        def on_tool_call_delta(self, delta, snapshot):
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

            self._message_output.cprint_update(str(snapshot.function))

        @override
        def on_tool_call_done(self, snapshot):
            self._message_output = None

            # TODO: add support for code interpreter and retrieval tools
            if snapshot.type != "function":
                return

            if snapshot.function.name == "SendMessage" and not (
                hasattr(
                    self._agency.send_message_tool_class.ToolConfig,
                    "output_as_result",
                )
                and self._agency.send_message_tool_class.ToolConfig.output_as_result
            ):
                try:
                    args = eval(snapshot.function.arguments)
                    recipient = args["recipient"]
                    self._message_output = MessageOutputLive(
                        "text", self.recipient_agent_name, recipient, ""
                    )

                    self._message_output.cprint_update(args["message"])
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
                    self._message_output = MessageOutputLive(
                        "function_output",
                        tool_call.function.name,
                        self.recipient_agent_name,
                        tool_call.function.output,
                    )
                    self._message_output.cprint_update(tool_call.function.output)

                self._message_output = None

        @override
        def on_end(self):
            self._message_output = None

    return TermEventHandler
