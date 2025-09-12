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

    def __init__(self, show_reasoning: bool = True):
        # Dictionary to hold agent-to-agent communication data
        self.agent_to_agent_communication: dict[str, dict[str, Any]] = {}
        # Dictionary to hold MCP call names
        self.mcp_calls: dict[str, str] = {}
        self.response_buffer: str = ""
        self.message_output: Live | None = None
        self.console = Console()
        self.last_live_display = None
        self.handoff_agent = None
        # Track whether final content has already been rendered for current live region
        self._final_rendered = False
        # Reasoning summary streaming state
        self.reasoning_output: Live | None = None
        self.reasoning_buffer: str = ""
        self._reasoning_final_rendered = False
        self.show_reasoning = bool(show_reasoning)

    def set_show_reasoning(self, enabled: bool) -> None:
        self.show_reasoning = bool(enabled)

    def _cleanup_live_display(self):
        """Clean up any active Live display safely."""
        if self.message_output is not None:
            try:
                self.message_output.__exit__(None, None, None)
            except Exception:
                pass  # Ignore cleanup errors
            self.message_output = None
            self.response_buffer = ""
            self._final_rendered = False
        if self.reasoning_output is not None:
            try:
                self.reasoning_output.__exit__(None, None, None)
            except Exception:
                pass
            self.reasoning_output = None
            self.reasoning_buffer = ""
            self._reasoning_final_rendered = False

    def _update_console(self, msg_type: str, sender: str, receiver: str, content: str, add_separator: bool = True):
        # Print a separator only for function, function_output, and agent-to-agent messages
        emoji = "👤" if sender.lower() == "user" else "🤖"
        if msg_type == "function":
            header = f"{emoji} {sender} 🛠️ Executing Function"
        elif msg_type == "function_output":
            header = f"{sender} ⚙️ Function Output"
        else:
            header = f"{emoji} {sender} 🗣️ @{receiver}"
        self.console.print(f"[bold]{header}[/bold]\n{content}")
        if add_separator:
            self.console.rule()

    def openai_to_message_output(self, event: Any, recipient_agent: str):
        try:
            # Reset any stale handoff state at the start of a new response lifecycle
            if getattr(event, "type", None) == "raw_response_event" and hasattr(event, "data"):
                data_type = getattr(event.data, "type", None)
                if data_type == "response.created":
                    self.handoff_agent = None
            # Use agent from event if available, otherwise fall back to recipient_agent
            agent_name = self.handoff_agent or getattr(event, "agent", None) or recipient_agent
            caller_agent = getattr(event, "callerAgent", None)
            # Determine who the agent is speaking to (if caller_agent exists, respond to them, else to user)
            speaking_to = caller_agent if caller_agent else "user"

            if hasattr(event, "data"):
                event_type = event.type
                if event_type == "raw_response_event":
                    data = event.data
                    data_type = data.type
                    # --- Reasoning summary streaming (o-series models) ---
                    if data_type == "response.reasoning_summary_text.delta":
                        if not self.show_reasoning:
                            return
                        try:
                            delta_text = getattr(data, "delta", "") or ""
                        except Exception:
                            delta_text = ""
                        if len(str(delta_text)) < 1:
                            return
                        # Initialize reasoning live region when first non-empty delta arrives
                        if self.reasoning_output is None:
                            self.reasoning_buffer = ""
                            self._reasoning_final_rendered = False
                            self.reasoning_output = Live("", console=self.console, refresh_per_second=10)
                            self.reasoning_output.__enter__()
                        self.reasoning_buffer += str(delta_text)
                        if self.reasoning_output is not None:
                            header_text = f"🧠 {agent_name} Reasoning"
                            md_content = Markdown(self.reasoning_buffer)
                            self.reasoning_output.update(Group(header_text, md_content))
                        return
                    elif data_type == "response.reasoning_summary_part.added":
                        if not self.show_reasoning:
                            return
                        # Open reasoning region early if the model announces a reasoning part
                        if self.reasoning_output is None:
                            self.reasoning_buffer = ""
                            self._reasoning_final_rendered = False
                            self.reasoning_output = Live("", console=self.console, refresh_per_second=10)
                            self.reasoning_output.__enter__()
                            header_text = f"🧠 {agent_name} Reasoning"
                            self.reasoning_output.update(Group(header_text, Markdown(self.reasoning_buffer)))
                        return
                    elif data_type == "response.reasoning_summary_part.done":
                        if not self.show_reasoning:
                            return
                        # Final text for the reasoning summary is provided in part.text
                        try:
                            part = getattr(data, "part", None)
                            final_text = getattr(part, "text", "") if part else ""
                        except Exception:
                            final_text = ""
                        if self.reasoning_output is None:
                            self.reasoning_output = Live("", console=self.console, refresh_per_second=10)
                            self.reasoning_output.__enter__()
                        self.reasoning_buffer = str(final_text)
                        header_text = f"🧠 {agent_name} Reasoning"
                        md_content = Markdown(self.reasoning_buffer)
                        self.reasoning_output.update(Group(header_text, md_content))
                        self._reasoning_final_rendered = True
                        try:
                            self.reasoning_output.__exit__(None, None, None)
                        except Exception:
                            pass
                        self.reasoning_output = None
                        self.reasoning_buffer = ""
                        self._reasoning_final_rendered = False
                        return
                    if data_type == "response.output_text.delta":
                        # If reasoning region is still open, finalize and close it before normal output
                        if self.reasoning_output is not None:
                            try:
                                if (not self._reasoning_final_rendered) and self.reasoning_buffer.strip():
                                    header_text_r = f"🧠 {agent_name} Reasoning"
                                    md_content_r = Markdown(self.reasoning_buffer)
                                    self.reasoning_output.update(Group(header_text_r, md_content_r))
                                self.reasoning_output.__exit__(None, None, None)
                            except Exception:
                                pass
                            self.reasoning_output = None
                            self.reasoning_buffer = ""
                            self._reasoning_final_rendered = False
                        # Skip empty deltas entirely to avoid rendering blank messages
                        try:
                            delta_text = getattr(data, "delta", "") or ""
                        except Exception:
                            delta_text = ""
                        if len(str(delta_text)) < 1:
                            return
                        # Use Live as a context manager for the live region only when we have non-empty text
                        if self.message_output is None:
                            self.response_buffer = ""
                            self._final_rendered = False
                            self.message_output = Live("", console=self.console, refresh_per_second=10)
                            self.message_output.__enter__()
                        self.response_buffer += str(delta_text)
                        if self.message_output is not None:
                            header_text = f"🤖 {agent_name} 🗣️ @{speaking_to}"
                            md_content = Markdown(self.response_buffer)
                            self.message_output.update(Group(header_text, md_content))
                    elif data_type in ["response.output_text.done", "response.content_part.done"]:
                        # Only render final content if there's actually something to show
                        if self.message_output is not None:
                            if self.response_buffer.strip():
                                header_text = f"🤖 {agent_name} 🗣️ @{speaking_to}"
                                md_content = Markdown(self.response_buffer)
                                self.message_output.update(Group(header_text, md_content))
                                self._final_rendered = True
                            try:
                                self.message_output.__exit__(None, None, None)
                            except Exception:
                                pass
                        self.message_output = None
                        self.response_buffer = ""
                        # Clear any pending handoff agent after finalizing the text/content part
                        self.handoff_agent = None
                        # Also finalize and close any active reasoning region
                        if self.reasoning_output is not None:
                            try:
                                if self.reasoning_buffer.strip():
                                    header_text_r = f"🧠 {agent_name} Reasoning"
                                    md_content_r = Markdown(self.reasoning_buffer)
                                    self.reasoning_output.update(Group(header_text_r, md_content_r))
                                    self._reasoning_final_rendered = True
                                self.reasoning_output.__exit__(None, None, None)
                            except Exception:
                                pass
                            self.reasoning_output = None
                            self.reasoning_buffer = ""
                            self._reasoning_final_rendered = False

                    elif data_type == "response.output_item.added":
                        item = data.item
                        # If a reasoning item is added, open the reasoning region and seed content if present
                        if getattr(item, "type", "") == "reasoning":
                            if not self.show_reasoning:
                                return
                            if self.reasoning_output is None:
                                self.reasoning_buffer = ""
                                self._reasoning_final_rendered = False
                                self.reasoning_output = Live("", console=self.console, refresh_per_second=10)
                                self.reasoning_output.__enter__()
                            # Seed with any current summary text
                            try:
                                summaries = getattr(item, "summary", []) or []
                                current_text = getattr(summaries[0], "text", "") if summaries else ""
                            except Exception:
                                current_text = ""
                            if current_text:
                                self.reasoning_buffer = str(current_text)
                                header_text = f"🧠 {agent_name} Reasoning"
                                self.reasoning_output.update(Group(header_text, Markdown(self.reasoning_buffer)))
                        elif getattr(item, "type", "") == "mcp_call":
                            self.mcp_calls[item.id] = item.name

                    elif data_type == "response.mcp_call_arguments.done":
                        content = f"Calling {self.mcp_calls[data.item_id]} tool with: {data.arguments}"
                        self._update_console("function", agent_name, "user", content)
                        self.mcp_calls.pop(data.item_id)

                    elif data_type == "response.output_item.done":
                        # Finalize live region. If final wasn't already rendered, render once before closing.
                        if self.message_output is not None:
                            try:
                                if (not self._final_rendered) and self.response_buffer.strip():
                                    header_text = f"🤖 {agent_name} 🗣️ @{speaking_to}"
                                    md_content = Markdown(self.response_buffer)
                                    self.message_output.update(Group(header_text, md_content))
                                self.message_output.__exit__(None, None, None)
                            except Exception:
                                pass
                        self.message_output = None
                        self.response_buffer = ""
                        self._final_rendered = False
                        # Ensure reasoning region is finalized on item completion
                        item = data.item
                        if getattr(item, "type", "") == "reasoning":
                            # If we didn't receive deltas, use the item's final summary text
                            try:
                                summaries = getattr(item, "summary", []) or []
                                final_text = getattr(summaries[0], "text", "") if summaries else ""
                            except Exception:
                                final_text = ""
                            if self.reasoning_output is None:
                                self.reasoning_output = Live("", console=self.console, refresh_per_second=10)
                                self.reasoning_output.__enter__()
                            if final_text:
                                self.reasoning_buffer = str(final_text)
                            header_text_r = f"🧠 {agent_name} Reasoning"
                            md_content_r = Markdown(self.reasoning_buffer)
                            try:
                                self.reasoning_output.update(Group(header_text_r, md_content_r))
                                self._reasoning_final_rendered = True
                                self.reasoning_output.__exit__(None, None, None)
                            except Exception:
                                pass
                            self.reasoning_output = None
                            self.reasoning_buffer = ""
                            self._reasoning_final_rendered = False
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
                                self.handoff_agent = None
                            else:
                                if item.type == "mcp_call":
                                    self._update_console("function_output", agent_name, "user", item.output)
                                else:
                                    content = f"Calling {item.name} tool with: {item.arguments}"
                                    self._update_console("function", agent_name, "user", content)
                                    if "transfer_to_" in item.name:
                                        self.handoff_agent = item.name.replace("transfer_to_", "")

            # Tool outputs (except mcp calls)
            elif hasattr(event, "item"):
                event_type = event.type
                if event_type == "run_item_stream_event":
                    item = event.item
                    if item.type == "tool_call_output_item":
                        call_id = item.raw_item["call_id"]

                        if call_id in self.agent_to_agent_communication:
                            # The response has already been shown via streaming, so just clean up
                            self.agent_to_agent_communication.pop(call_id)
                            # Clear any pending handoff agent after tool output is processed
                            self.handoff_agent = None
                            # Don't display it again - it's already been shown
                        else:
                            self._update_console("function_output", agent_name, "user", str(item.output))
                    # Usually final output is not used, but in case of guardrail guidance, it will be returned
                    # before any delta events, so we can display it immediately
                    elif item.type == "message_output_item":
                        raw_item = item.raw_item
                        if raw_item.id == "msg_input_guardrail_guidance":
                            self._update_console(
                                "text", agent_name, speaking_to, str(raw_item.content[0].text), add_separator=False
                            )

            # Handle error events (dict format from agent streaming)
            elif isinstance(event, dict) and event.get("type") == "error":
                self._cleanup_live_display()
                content = event.get("content", "Unknown error")
                print(f"\nEncountered error during streaming: {content}")
        except Exception as e:
            # Clean up any active Live display and log the error
            self._cleanup_live_display()
            print(f"\nError processing event: {e}")
