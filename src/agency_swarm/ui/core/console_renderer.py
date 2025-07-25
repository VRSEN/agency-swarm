"""
UI configuration for the terminal demo.
"""

from typing import Literal

from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown


class ConsoleRenderer:
    def __init__(
        self,
        msg_type: Literal["function", "function_output", "text", "system"],
        sender_name: str,
        receiver_name: str,
        content,
        console: Console | None = None,
    ):
        """Initialize a console renderer for messages.

        Args:
            msg_type: Type of message (function, function_output, text, system).
            sender_name: Name of the sender.
            receiver_name: Name of the receiver.
            content: Message content.
            console: Rich console instance. Defaults to new Console().
        """
        self.msg_type = msg_type
        self.sender_name = str(sender_name)
        self.receiver_name = str(receiver_name)
        self.content = str(content)
        self.console = console or Console()

    def cprint(self):
        """Print the message to console with formatting."""
        self.console.rule()
        header_text = self._get_header()
        md_content = Markdown(self.content)
        self.console.print(Group(header_text, md_content), end="")

    def _get_header(self):
        """Generate formatted header with emoji and message info."""
        emoji = self._get_emoji()

        if self.msg_type == "function":
            return f"{emoji} {self.sender_name} 🛠️ Executing Function"
        elif self.msg_type == "function_output":
            return f"{self.sender_name} ⚙️ Function Output"
        else:
            return f"{emoji} {self.sender_name} 🗣️ @{self.receiver_name}"

    def _get_emoji(self):
        """Get appropriate emoji for sender."""
        if self.msg_type == "system":
            return "🔧"

        name = self.sender_name.lower()
        if self.msg_type == "function_output":
            name = self.receiver_name.lower()

        return "👤" if name == "user" else "🤖"


class LiveConsoleRenderer(ConsoleRenderer):
    def __init__(self, msg_type, sender_name, receiver_name, content, console=None):
        """Initialize live console renderer with streaming display."""
        super().__init__(msg_type, sender_name, receiver_name, content, console)
        self.live_display = Live(vertical_overflow="visible")
        self.live_display.start()
        self.console.rule()

    def __del__(self):
        """Clean up live display on deletion."""
        if hasattr(self, "live_display") and self.live_display:
            self.live_display.stop()

    def cprint_update(self, snapshot):
        """Update live display with new content."""
        self.content = snapshot or "No content available"

        try:
            header_text = self._get_header()
            md_content = Markdown(self.content)
            self.live_display.update(Group(header_text, md_content))
        except Exception as e:
            if "string index out of range" not in str(e):
                raise
