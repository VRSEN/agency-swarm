from __future__ import annotations

import json
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown


class ConsoleEventAdapter:
    """
    Converts OpenAI Agents SDK events int console message outputs.
    """

    def __init__(self):
        # Dictionary to hold agent-to-agent communication data
        self.agent_to_agent_communication: dict[str, dict[str, Any]] = {}
        # Dictionary to hold MCP call names
        self.mcp_calls: dict[str, str] = {}
        self.response_buffer = ""
        self.message_output = None
        self.console = Console()
        self.last_live_display = None

    def _cleanup_live_display(self):
        """Clean up any active Live display safely."""
        if self.message_output is not None:
            try:
                self.message_output.__exit__(None, None, None)
            except Exception:
                pass  # Ignore cleanup errors
            self.message_output = None
            self.response_buffer = ""

    def _update_console(self, msg_type: str, sender: str, receiver: str, content: str):
        # Print a separator only for function, function_output, and agent-to-agent messages
        emoji = "👤" if sender.lower() == "user" else "🤖"
        if msg_type == "function":
            header = f"{emoji} {sender} 🛠️ Executing Function"
        elif msg_type == "function_output":
            header = f"{sender} ⚙️ Function Output"
        else:
            header = f"{emoji} {sender} 🗣️ @{receiver}"
        self.console.print(f"[bold]{header}[/bold]\n{content}")
        self.console.rule()

    def openai_to_message_output(self, event: Any, recipient_agent: str):
        try:
            # Use agent from event if available, otherwise fall back to recipient_agent
            agent_name = getattr(event, "agent", None) or recipient_agent
            caller_agent = getattr(event, "callerAgent", None)
            # Determine who the agent is speaking to (if caller_agent exists, respond to them, else to user)
            speaking_to = caller_agent if caller_agent else "user"

            if hasattr(event, "data"):
                event_type = event.type
                if event_type == "raw_response_event":
                    data = event.data
                    data_type = data.type
                    if data_type == "response.output_text.delta":
                        # Use Live as a context manager for the live region
                        if self.message_output is None:
                            self.response_buffer = ""
                            self.message_output = Live("", console=self.console, refresh_per_second=10)
                            self.message_output.__enter__()
                        self.response_buffer += data.delta
                        header_text = f"🤖 {agent_name} 🗣️ @{speaking_to}"
                        md_content = Markdown(self.response_buffer)
                        self.message_output.update(Group(header_text, md_content))
                    elif data_type == "response.output_text.done":
                        if self.message_output is not None:
                            header_text = f"🤖 {agent_name} 🗣️ @{speaking_to}"
                            md_content = Markdown(self.response_buffer)
                            self.message_output.update(Group(header_text, md_content))
                            self.message_output.__exit__(None, None, None)
                        self.message_output = None
                        self.response_buffer = ""

                    elif data_type == "response.output_item.added":
                        if data.item.type == "mcp_call":
                            self.mcp_calls[data.item.id] = data.item.name

                    elif data_type == "response.mcp_call_arguments.done":
                        content = f"Calling {self.mcp_calls[data.item_id]} tool with: {data.arguments}"
                        self._update_console("function", agent_name, "user", content)
                        self.mcp_calls.pop(data.item_id)

                    elif data_type == "response.output_item.done":
                        self.message_output = None
                        item = data.item
                        if hasattr(item, "arguments"):
                            # Handle agent to agent communication
                            if item.name.startswith("send_message"):
                                # Unified tool - extract recipient from arguments
                                args = json.loads(item.arguments)
                                called_agent = args.get("recipient_agent", "Unknown")
                                message = args.get("message", "")
                                self._update_console("text", agent_name, called_agent, message)
                                self.agent_to_agent_communication[item.call_id] = {
                                    "sender": agent_name,
                                    "receiver": called_agent,
                                    "message": message,
                                }
                            else:
                                if item.type == "mcp_call":
                                    self._update_console("function_output", agent_name, "user", item.output)
                                else:
                                    content = f"Calling {item.name} tool with: {item.arguments}"
                                    self._update_console("function", agent_name, "user", content)

            # Tool outputs (except mcp calls)
            elif hasattr(event, "item"):
                event_type = event.type
                if event_type == "run_item_stream_event":
                    item = event.item
                    if item.type in "tool_call_output_item":
                        call_id = item.raw_item["call_id"]

                        if call_id in self.agent_to_agent_communication:
                            # The response has already been shown via streaming, so just clean up
                            self.agent_to_agent_communication.pop(call_id)
                            # Don't display it again - it's already been shown
                        else:
                            self._update_console("function_output", agent_name, "user", str(item.output))

            # Handle error events (dict format from agent streaming)
            elif isinstance(event, dict) and event.get("type") == "error":
                self._cleanup_live_display()
                content = event.get("content", "Unknown error")
                print(f"\nEncountered error during streaming: {content}")
        except Exception as e:
            # Clean up any active Live display and log the error
            self._cleanup_live_display()
            print(f"\nError processing event: {e}")
