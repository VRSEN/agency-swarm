from typing import Literal
import hashlib
from rich.markdown import Markdown
from rich.console import Console

from agency_swarm.util.oai import get_openai_client

console = Console()

class MessageOutput:
    def __init__(self, msg_type: Literal["function", "function_output", "text", "system"], sender_name: str, receiver_name: str, content):
        self.msg_type = msg_type
        self.sender_name = str(sender_name)
        self.receiver_name = str(receiver_name)
        self.content = str(content)

        self.client = get_openai_client()

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

        emoji = self.get_sender_emoji()

        header = emoji + " " + self.get_formatted_header()

        # color = self.hash_names_to_color()

        console.print(header)

        md = Markdown(self.content)

        console.print(md)

    def get_formatted_header(self):
        if self.msg_type == "function":
            text = f"{self.sender_name} 🛠️ Executing Function"
            return text

        if self.msg_type == "function_output":
            text = f"{self.sender_name} ⚙️ Function Output"
            return text

        text = f"{self.sender_name} 🗣️ @{self.receiver_name}"

        return text

    def get_formatted_content(self):
        header = self.get_formatted_header()
        content = f"\n{self.content}\n"
        return header + content

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

