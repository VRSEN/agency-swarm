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

    def __init__(self, show_reasoning: bool = True, agents: list[str] | None = None):
        # Dictionary to hold agent-to-agent communication data
        self.agent_to_agent_communication: dict[str, dict[str, Any]] = {}
        # Dictionary to hold MCP call names
        self.mcp_calls: dict[str, str] = {}
        self.response_buffer: str = ""
        self.message_output: Live | None = None
        self.console = Console()
        self.last_live_display = None
        self.handoff_agent: str | None = None
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
        # Names of all agents in the agency, used to display correct names on handoffs
        self.agents = agents or []

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
            # Ensure live-rendering attributes exist before processing events
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

            # Reset handoff and flags at the start of a new response lifecycle
            if getattr(event, "type", None) == "raw_response_event" and hasattr(event, "data"):
                if getattr(event.data, "type", None) == "response.created":
                    self._reset_lifecycle_state()

            agent_name = self.handoff_agent or getattr(event, "agent", None) or recipient_agent
            caller_agent = getattr(event, "callerAgent", None)
            speaking_to = caller_agent if caller_agent else "user"

            if hasattr(event, "data"):
                if event.type == "raw_response_event":
                    self._handle_raw_response_event(event.data, agent_name, speaking_to)
            # Tool outputs (except mcp calls)
            elif hasattr(event, "item"):
                if event.type == "run_item_stream_event":
                    self._handle_run_item_stream_event(event.item, agent_name, speaking_to)
            elif isinstance(event, dict) and event.get("type") == "error":
                self._handle_error_dict_event(event)
        except Exception as e:
            self._cleanup_live_display()
            print(f"\nError processing event: {e}")

    # --- Private handlers (behavior preserved) ---
    def _reset_lifecycle_state(self) -> None:
        self._reasoning_displayed = False
        self._message_started = False
        self._reasoning_needs_separator = False

    def _handle_raw_response_event(self, data: Any, agent_name: str, speaking_to: str) -> None:
        data_type = getattr(data, "type", None)
        if data_type == "response.reasoning_summary_text.delta":
            if not self.show_reasoning:
                # Preserve legacy behavior: show header once even when reasoning is disabled
                if not self._reasoning_displayed:
                    header_text = f"[italic dim]🧠 {agent_name} Reasoning[/]"
                    try:
                        self.console.print(header_text)
                    except Exception:
                        pass
                    self._reasoning_displayed = True
                return
            try:
                delta_text = getattr(data, "delta", "") or ""
            except Exception:
                delta_text = ""
            if len(str(delta_text)) < 1:
                return
            if self.reasoning_output is None:
                self.reasoning_buffer = ""
                self._reasoning_final_rendered = False
                self.reasoning_output = Live("", console=self.console, refresh_per_second=10)
                self.reasoning_output.__enter__()
            if self._reasoning_needs_separator and self.reasoning_buffer:
                self.reasoning_buffer += "\n\n"
                self._reasoning_needs_separator = False
            self.reasoning_buffer += str(delta_text)
            if self.reasoning_output is not None:
                md_content = Markdown(self.reasoning_buffer, style="italic dim")
                header_text = f"[italic dim]🧠 {agent_name} Reasoning[/]\n"
                self.reasoning_output.update(Group(header_text, md_content))
                self._reasoning_displayed = True
            return
        elif data_type == "response.reasoning_summary_part.done":
            if not self.show_reasoning:
                return
            self._reasoning_final_rendered = True
            self._reasoning_needs_separator = True
            return
        elif data_type == "response.output_text.delta":
            self._finalize_open_reasoning()
            try:
                delta_text = getattr(data, "delta", "") or ""
            except Exception:
                delta_text = ""
            if len(str(delta_text)) < 1:
                return
            if self.message_output is None:
                self.response_buffer = ""
                self._final_rendered = False
                self.message_output = Live("", console=self.console, refresh_per_second=10)
                self.message_output.__enter__()
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
            self._finalize_open_reasoning()
        elif data_type == "response.output_item.added":
            self._handle_output_item_added(data.item, agent_name)
        elif data_type == "response.mcp_call_arguments.done":
            self._handle_mcp_call_arguments_done(data, agent_name)
        elif data_type == "response.output_item.done":
            self._handle_output_item_done(data, agent_name, speaking_to)

    def _finalize_open_reasoning(self) -> None:
        if self.reasoning_output is not None:
            try:
                self.reasoning_output.__exit__(None, None, None)
            except Exception:
                pass
            self.reasoning_output = None
            self.reasoning_buffer = ""
            self._reasoning_final_rendered = True

    def _handle_output_item_added(self, item: Any, agent_name: str) -> None:
        if getattr(item, "type", "") == "reasoning":
            if not self.show_reasoning:
                # Preserve legacy behavior: show header once even when reasoning is disabled
                if not self._reasoning_displayed:
                    header_text = f"[italic dim]🧠 {agent_name} Reasoning[/]"
                    try:
                        self.console.print(header_text)
                    except Exception:
                        pass
                    self._reasoning_displayed = True
                return
            try:
                summaries = getattr(item, "summary", []) or []
                current_text = getattr(summaries[0], "text", "") if summaries else ""
            except Exception:
                current_text = ""
            if current_text:
                self.reasoning_buffer = (
                    f"{self.reasoning_buffer}\n\n{current_text}" if self.reasoning_buffer else str(current_text)
                )
                if self.reasoning_output is None:
                    self.reasoning_output = Live("", console=self.console, refresh_per_second=10)
                    self.reasoning_output.__enter__()
                    self._reasoning_final_rendered = False
                header_text = f"[italic dim]🧠 {agent_name} Reasoning[/]\n"
                self.reasoning_output.update(
                    Group(
                        header_text,
                        Markdown(self.reasoning_buffer, style="italic dim"),
                    )
                )
                self._reasoning_displayed = True
                self._reasoning_needs_separator = False
            elif self.reasoning_output is None:
                self.reasoning_buffer = ""
                self._reasoning_final_rendered = False
        elif getattr(item, "type", "") == "mcp_call":
            self.mcp_calls[item.id] = item.name

    def _handle_mcp_call_arguments_done(self, data: Any, agent_name: str) -> None:
        content = f"Calling {self.mcp_calls[data.item_id]} tool with: {data.arguments}"
        self._update_console("function", agent_name, "user", content)
        self.mcp_calls.pop(data.item_id)

    def _handle_output_item_done(self, data: Any, agent_name: str, speaking_to: str) -> None:
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

        item = data.item
        if getattr(item, "type", "") == "reasoning":
            try:
                summaries = getattr(item, "summary", []) or []
                final_text = getattr(summaries[0], "text", "") if summaries else ""
            except Exception:
                final_text = ""
            if final_text:
                self.reasoning_buffer = str(final_text)
            if self.reasoning_buffer:
                if self.reasoning_output is None:
                    self.reasoning_output = Live("", console=self.console, refresh_per_second=10)
                    self.reasoning_output.__enter__()
                header_text_r = f"[italic dim]🧠 {agent_name} Reasoning[/]\n"
                try:
                    if not self._reasoning_final_rendered:
                        md_content_r = Markdown(self.reasoning_buffer, style="italic dim")
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
            if item.name.startswith("send_message"):
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
                        tool_handoff_name = item.name.replace("transfer_to_", "")
                        self.handoff_agent = tool_handoff_name
                        # Try to restore the correct agent name if it was split by underscores
                        try:
                            for agent in self.agents:
                                # Compare with underscores treated as spaces for robustness
                                if str(agent).replace("_", " ") == tool_handoff_name.replace("_", " "):
                                    self.handoff_agent = str(agent)
                                    break
                        except Exception:
                            # If self.agents is not iterable or any issue occurs, keep tool_handoff_name
                            pass

    def _handle_run_item_stream_event(self, item: Any, agent_name: str, speaking_to: str) -> None:
        if item.type == "tool_call_output_item":
            call_id = item.raw_item["call_id"]
            if call_id in self.agent_to_agent_communication:
                self.agent_to_agent_communication.pop(call_id)
                self.handoff_agent = None
            else:
                self._update_console("function_output", agent_name, "user", str(item.output))
        elif item.type == "message_output_item":
            raw_item = item.raw_item
            if raw_item.id == "msg_input_guardrail_guidance":
                self._update_console(
                    "text", agent_name, speaking_to, str(raw_item.content[0].text), add_separator=False
                )

    def _handle_error_dict_event(self, event: dict) -> None:
        self._cleanup_live_display()
        content = event.get("content", "Unknown error")
        print(f"\nEncountered error during streaming: {content}")
