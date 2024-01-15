from typing import Literal
import hashlib
from rich.console import Console

from agency_swarm.util.oai import get_openai_client

console = Console()

send2func = False
send2rec = False
send2recdic = dict()

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
            'green', 'yellow', 'blue', 'magenta', 'cyan', 'white',
        ]
        color_index = hash_int % len(colors)
        return colors[color_index]

    def cprint(self):

        console.rule()
        emoji = self.get_sender_emoji()

        header = emoji + self.get_formatted_header()

        color = self.hash_names_to_color()

        console.print(header, style=color)

        console.print(str(self.content), style=color)

    def get_formatted_header(self):
        global send2rec
        global send2func
        
        if self.msg_type == "function":
            text = f"{self.sender_name} 🛠️ Executing Function"
            send2func = True
            send2rec = False
            return text

        if self.msg_type == "function_output":
            text = f"{self.sender_name} ⚙️Function Output"
            send2rec = False
            return text

        if send2rec == True:
            if send2recdic.get((self.sender_name, self.receiver_name)) == None:
                send2recdic[(self.sender_name, self.receiver_name)] = 0
            send2recdic[(self.sender_name, self.receiver_name)] += 1

        if send2rec == False and send2recdic.get((self.receiver_name, self.sender_name)) != None and send2recdic.get((self.receiver_name, self.sender_name)) > 0:
            text = f"{self.sender_name} 🙋 @{self.receiver_name}"
            send2recdic[(self.receiver_name, self.sender_name)] -= 1
            return text
            
        text = f"{self.sender_name} 🗣️ @{self.receiver_name}"
        send2rec = False
        return text

    def get_formatted_content(self):
        global send2func
        global send2rec
        header = self.get_formatted_header()
        #print(self.content.find("name=\'SendMessage\'"))
        if send2func == True and self.content.find("name=\'SendMessage\'") != -1:
            send2rec = True
        send2func = False
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

