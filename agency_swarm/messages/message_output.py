from typing import Literal
import hashlib
from termcolor import colored

from agency_swarm.util.oai import get_openai_client


class MessageOutput:
    def __init__(self, msg_type: Literal["function", "function_output", "text", "system"], sender_name: str, receiver_name: str, content):
        self.msg_type = msg_type
        self.sender_name = str(sender_name)
        self.receiver_name = str(receiver_name)
        self.content = str(content)

        self.client = get_openai_client()

    def hash_names_to_color(self):
        if self.msg_type == "function":
            return "green"

        if self.msg_type == "system":
            return "red"

        combined_str = self.sender_name + self.receiver_name
        encoded_str = combined_str.encode()
        hash_obj = hashlib.md5(encoded_str)
        hash_int = int(hash_obj.hexdigest(), 16)
        colors = [
            'grey', 'yellow', 'blue', 'magenta', 'cyan', 'white',
        ]
        color_index = hash_int % len(colors)
        return colors[color_index]

    def cprint(self):
        color = self.hash_names_to_color()

        text = self.get_formatted_content()

        print(colored(text, color))

    def get_formatted_content(self):
        if self.msg_type == "function":
            text = self.sender_name + " Executing Function: " + str(self.content) + "\n"
            return text

        if self.msg_type == "function_output":
            text = self.sender_name + f"Function Output (by {self.receiver_name}): " + str(self.content) + "\n"
            return text

        text = self.sender_name + f' (to {self.receiver_name})' ": " + self.content + "\n"
        return text

    def get_sender_emoji(self):
        if self.msg_type == "function":
            return "🧠"
        if self.msg_type == "system":
            return "🤖"

        if self.sender_name.lower() == "user":
            return "👤"

        if self.sender_name.lower() == "ceo":
            return "🤵‍"

        # output emoji based on hash of sender name
        encoded_str = self.sender_name.encode()
        hash_obj = hashlib.md5(encoded_str)
        hash_int = int(hash_obj.hexdigest(), 16)
        emojis = [
            '🐶', '🐱', '🐭', '🐹', '🐰', '🦊',
            '🐻', '🐼', '🐨', '🐯', '🦁', '🐮',
            '🐷', '🐸', '🐵', '🐔', '🐧', '🐦',
            '🐤']

        emoji_index = hash_int % len(emojis)

        return emojis[emoji_index]

