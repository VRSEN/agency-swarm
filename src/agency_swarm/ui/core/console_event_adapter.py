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
        self._reasoning_displayed = False
        self._message_started = False
        self._reasoning_needs_separator = False
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
        sender_emoji = "👤" if sender.lower() == "user" else "🤖"
        receiver_emoji = "👤" if receiver.lower() == "user" else "🤖"
        if msg_type == "function":
            header = f"{sender_emoji} {sender} 🛠️ Executing Function"
        elif msg_type == "function_output":
            header = f"{sender} ⚙️ Function Output"
        else:
            header = f"{sender_emoji} {sender} → {receiver_emoji} {receiver}"
        self.console.print(f"[bold]{header}[/bold]\n{content}")
        if add_separator:
            self.console.rule()

    def openai_to_message_output(self, event: Any, recipient_agent: str):
        try:
            # Ensure essential attributes exist when bound to a MagicMock in tests
            # (MagicMock returns new mocks for missing attributes which can break type checks)
            self_dict = getattr(self, "__dict__", {})
            if "reasoning_output" not in self_dict:
                self.reasoning_output = None
            if "reasoning_buffer" not in self_dict:
                self.reasoning_buffer = ""
            if "_reasoning_final_rendered" not in self_dict:
                self._reasoning_final_rendered = False
            if "_reasoning_displayed" not in self_dict:
                self._reasoning_displayed = False
            if "_message_started" not in self_dict:
                self._message_started = False
            if "_reasoning_needs_separator" not in self_dict:
                self._reasoning_needs_separator = False
            if "message_output" not in self_dict:
                self.message_output = None
            if "response_buffer" not in self_dict:
                self.response_buffer = ""

            # Reset any stale handoff state at the start of a new response lifecycle
            if getattr(event, "type", None) == "raw_response_event" and hasattr(event, "data"):
                data_type = getattr(event.data, "type", None)
                if data_type == "response.created":
                    self.handoff_agent = None
                    # Reset display flags for new response lifecycle
                    self._reasoning_displayed = False
                    self._message_started = False
                    self._reasoning_needs_separator = False
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
                        # Insert a blank-line separator when starting a new reasoning part
                        if self._reasoning_needs_separator and self.reasoning_buffer:
                            self.reasoning_buffer += "\n\n"
                            self._reasoning_needs_separator = False
                        self.reasoning_buffer += str(delta_text)
                        if self.reasoning_output is not None:
                            md_content = Markdown(self.reasoning_buffer, style="italic dim")
                            header_text = f"[italic dim]🧠 {agent_name} Reasoning[/]\n"
                            # Always render header + content so header stays visible across updates
                            self.reasoning_output.update(Group(header_text, md_content))
                            self._reasoning_displayed = True
                        return
                    # Do not add any messages here - they were rendered via deltas
                    elif data_type == "response.reasoning_summary_part.done":
                        if not self.show_reasoning:
                            return
                        # Mark the current reasoning part as finalized but keep the Live region open
                        # so subsequent reasoning parts can continue under the same header.
                        self._reasoning_final_rendered = True
                        self._reasoning_needs_separator = True
                        return
                    if data_type == "response.output_text.delta":
                        # If reasoning region is still open, finalize and close it before normal output
                        if self.reasoning_output is not None:
                            try:
                                # Close the reasoning region before normal output begins
                                self.reasoning_output.__exit__(None, None, None)
                            except Exception:
                                pass
                            self.reasoning_output = None
                            # Keep buffer cleared for next turn
                            self.reasoning_buffer = ""
                            self._reasoning_final_rendered = True
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
                            # Visually separate from any preceding reasoning block
                            if self._reasoning_displayed and not self._message_started:
                                try:
                                    self.console.print("")
                                except Exception:
                                    pass
                        self.response_buffer += str(delta_text)
                        if self.message_output is not None:
                            sender_emoji = "👤" if str(agent_name).lower() == "user" else "🤖"
                            receiver_emoji = "👤" if str(speaking_to).lower() == "user" else "🤖"
                            header_text = f"{sender_emoji} {agent_name} → {receiver_emoji} {speaking_to}"
                            md_content = Markdown(self.response_buffer)
                            self.message_output.update(Group(header_text, md_content))
                            self._message_started = True
                    elif data_type in ["response.output_text.done", "response.content_part.done"]:
                        # Only render final content if there's actually something to show
                        if self.message_output is not None:
                            if self.response_buffer.strip():
                                sender_emoji = "👤" if str(agent_name).lower() == "user" else "🤖"
                                receiver_emoji = "👤" if str(speaking_to).lower() == "user" else "🤖"
                                header_text = f"{sender_emoji} {agent_name} → {receiver_emoji} {speaking_to}"
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
                                # Avoid repeating the reasoning header/content at finalization
                                self._reasoning_final_rendered = True
                                self.reasoning_output.__exit__(None, None, None)
                            except Exception:
                                pass
                            self.reasoning_output = None
                            self.reasoning_buffer = ""

                    elif data_type == "response.output_item.added":
                        item = data.item
                        # If a reasoning item is added, open the reasoning region and seed content if present
                        if getattr(item, "type", "") == "reasoning":
                            if not self.show_reasoning:
                                return
                            # Seed with any current summary text
                            try:
                                summaries = getattr(item, "summary", []) or []
                                current_text = getattr(summaries[0], "text", "") if summaries else ""
                            except Exception:
                                current_text = ""
                            if current_text:
                                # Append to existing buffer with a blank line separator if needed
                                self.reasoning_buffer = (
                                    f"{self.reasoning_buffer}\n\n{current_text}"
                                    if self.reasoning_buffer
                                    else str(current_text)
                                )
                                # Ensure Live display exists
                                if self.reasoning_output is None:
                                    self.reasoning_output = Live("", console=self.console, refresh_per_second=10)
                                    self.reasoning_output.__enter__()
                                    self._reasoning_final_rendered = False
                                # Always render header + content so header remains visible
                                header_text = f"[italic dim]🧠 {agent_name} Reasoning[/]\n"
                                self.reasoning_output.update(
                                    Group(
                                        header_text,
                                        Markdown(
                                            self.reasoning_buffer,
                                            style="italic dim",
                                        ),
                                    )
                                )
                                self._reasoning_displayed = True
                                self._reasoning_needs_separator = False
                            elif self.reasoning_output is None:
                                # Initialize buffer but don't create Live display yet
                                self.reasoning_buffer = ""
                                self._reasoning_final_rendered = False
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
                                    sender_emoji = "👤" if str(agent_name).lower() == "user" else "🤖"
                                    receiver_emoji = "👤" if str(speaking_to).lower() == "user" else "🤖"
                                    header_text = f"{sender_emoji} {agent_name} → {receiver_emoji} {speaking_to}"
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
                            if final_text:
                                self.reasoning_buffer = str(final_text)
                            # Only create and show reasoning display if there's actual content
                            if self.reasoning_buffer:
                                if self.reasoning_output is None:
                                    self.reasoning_output = Live("", console=self.console, refresh_per_second=10)
                                    self.reasoning_output.__enter__()
                                header_text_r = f"[italic dim]🧠 {agent_name} Reasoning[/]\n"
                                try:
                                    if not self._reasoning_final_rendered:
                                        md_content_r = Markdown(self.reasoning_buffer, style="italic dim")
                                        # Always render header + content to preserve header visibility
                                        self.reasoning_output.update(Group(header_text_r, md_content_r))
                                        self._reasoning_displayed = True
                                        self._reasoning_final_rendered = True
                                    self.reasoning_output.__exit__(None, None, None)
                                except Exception:
                                    pass
                                self.reasoning_output = None
                                self.reasoning_buffer = ""
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
