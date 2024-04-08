from typing import Literal
import hashlib
from rich.markdown import Markdown
from rich.console import Console, Group
from rich.live import Live

console = Console()
live_display = Live()

class MessageOutput:
    def __init__(self, msg_type: Literal["function", "function_output", "text", "system"], sender_name: str,
                 receiver_name: str, content):
        self.msg_type = msg_type
        self.sender_name = str(sender_name)
        self.receiver_name = str(receiver_name)
        self.content = str(content)

    def hash_names_to_color(self):
        if self.msg_type == "function" or self.msg_type == "function_output":
            return "dim"

        if self.msg_type == "system":
            return "red"

        combined_str = self.sender_name + self.receiver_name
        encoded_str = combined_str.encode()
        hash_obj = hashlib.md5(encoded_str)
        hash_int = int(hash_obj.hexdigest(), 16)
        colors = [
            'green', 'yellow', 'blue', 'magenta', 'cyan', 'bright_white',
        ]
        color_index = hash_int % len(colors)
        return colors[color_index]

    def cprint(self):
        console.rule()

        header_text = self.sender_emoji + " " + self.formatted_header
        md_content = Markdown(self.content)

        render_group = Group(header_text, md_content)

        console.print(render_group, end="")

    @property
    def formatted_header(self):
        return self.get_formatted_header()

    def get_formatted_header(self):
        if self.msg_type == "function":
            text = f"{self.sender_emoji} {self.sender_name} 🛠️ Executing Function"
            return text

        if self.msg_type == "function_output":
            text = f"{self.sender_name} ⚙️ Function Output"
            return text

        text = f"{self.sender_emoji} {self.sender_name} 🗣️ @{self.receiver_name}"

        return text

    def get_formatted_content(self):
        header = self.get_formatted_header()
        content = f"\n{self.content}\n"
        return header + content

    @property
    def sender_emoji(self):
        return self.get_sender_emoji()

    def get_sender_emoji(self):
        if self.msg_type == "system":
            return "🤖"

        sender_name = self.sender_name.lower()
        if self.msg_type == "function_output":
            sender_name = self.receiver_name.lower()

        if sender_name == "user":
            return "👤"

        if sender_name == "ceo":
            return "🤵"

        # output emoji based on hash of sender name
        encoded_str = sender_name.encode()
        hash_obj = hashlib.md5(encoded_str)
        hash_int = int(hash_obj.hexdigest(), 16)
        emojis = [
            '🐶', '🐱', '🐭', '🐹', '🐰', '🦊',
            '🐻', '🐼', '🐨', '🐯', '🦁', '🐮',
            '🐷', '🐸', '🐵', '🐔', '🐧', '🐦',
            '🐤']

        emoji_index = hash_int % len(emojis)

        return emojis[emoji_index]


class MessageOutputLive(MessageOutput):
    live_display = None

    def __init__(self, msg_type: Literal["function", "function_output", "text", "system"], sender_name: str,
                 receiver_name: str, content):
        super().__init__(msg_type, sender_name, receiver_name, content)
        # Initialize Live display if not already done
        self.live_display = Live(vertical_overflow="visible")
        self.live_display.start()

        console.rule()

    def __del__(self):
        self.live_display.stop()
        self.live_display = None

    def cprint_update(self, snapshot):
        """
        Update the display with new snapshot content.
        """
        self.content = snapshot  # Update content with the latest snapshot

        header_text = self.formatted_header
        md_content = Markdown(self.content)

        # Creating a group of renderables for the live display
        render_group = Group(header_text, md_content)

        # Update the Live display
        self.live_display.update(render_group)
