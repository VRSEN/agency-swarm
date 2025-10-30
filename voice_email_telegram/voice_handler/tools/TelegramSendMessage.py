from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

class TelegramSendMessage(BaseTool):
    """
    Sends a text message to a Telegram chat.
    Supports markdown/HTML formatting and inline keyboards for interactive buttons.
    """

    chat_id: str = Field(
        ...,
        description="Telegram chat ID to send message to"
    )

    text: str = Field(
        ...,
        description="Message text to send (supports Markdown or HTML)"
    )

    parse_mode: str = Field(
        default="Markdown",
        description="Text parsing mode: 'Markdown', 'MarkdownV2', or 'HTML'"
    )

    reply_markup: str = Field(
        default="",
        description="Optional JSON string for inline keyboard or reply keyboard"
    )

    def run(self):
        """
        Sends the message via Telegram Bot API.
        Returns JSON string with message details.
        """
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            return json.dumps({
                "error": "TELEGRAM_BOT_TOKEN not found in environment variables"
            })

        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            payload = {
                "chat_id": self.chat_id,
                "text": self.text,
                "parse_mode": self.parse_mode
            }

            # Add reply markup if provided
            if self.reply_markup:
                try:
                    reply_markup_data = json.loads(self.reply_markup)
                    payload["reply_markup"] = json.dumps(reply_markup_data)
                except json.JSONDecodeError:
                    return json.dumps({
                        "error": "Invalid JSON in reply_markup parameter"
                    })

            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                return json.dumps({
                    "error": f"Telegram API error: {data.get('description', 'Unknown error')}"
                })

            result = {
                "success": True,
                "message_id": data["result"]["message_id"],
                "chat_id": data["result"]["chat"]["id"],
                "date": data["result"]["date"],
                "text_sent": self.text[:100] + "..." if len(self.text) > 100 else self.text
            }

            return json.dumps(result, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"Failed to send message: {str(e)}"
            })
        except Exception as e:
            return json.dumps({
                "error": f"Error sending message: {str(e)}"
            })


if __name__ == "__main__":
    print("Testing TelegramSendMessage...")

    # Test 1: Check for token
    print("\n1. Check TELEGRAM_BOT_TOKEN:")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        print(f"Token found (starts with): {token[:10]}...")
    else:
        print("Warning: TELEGRAM_BOT_TOKEN not set")

    # Test 2: Simple message
    print("\n2. Test simple message:")
    tool = TelegramSendMessage(
        chat_id="12345",
        text="Hello! This is a test message."
    )
    result = tool.run()
    print(result)

    # Test 3: Message with Markdown
    print("\n3. Test message with Markdown:")
    tool = TelegramSendMessage(
        chat_id="12345",
        text="*Bold text* and _italic text_\n\nHere's a [link](https://example.com)",
        parse_mode="Markdown"
    )
    result = tool.run()
    print(result)

    # Test 4: Message with inline keyboard
    print("\n4. Test message with inline keyboard:")
    inline_keyboard = json.dumps({
        "inline_keyboard": [
            [
                {"text": "✅ Approve", "callback_data": "approve:draft_123"},
                {"text": "❌ Reject", "callback_data": "reject:draft_123"}
            ]
        ]
    })
    tool = TelegramSendMessage(
        chat_id="12345",
        text="📧 *Email Draft Ready*\n\nWhat would you like to do?",
        parse_mode="Markdown",
        reply_markup=inline_keyboard
    )
    result = tool.run()
    print(result)

    # Test 5: Long message
    print("\n5. Test long message:")
    long_text = "This is a long message. " * 50  # Repeat to make it long
    tool = TelegramSendMessage(
        chat_id="12345",
        text=long_text
    )
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nUsage notes:")
    print("- Get chat_id from TelegramGetUpdates response")
    print("- Use Markdown for formatting: *bold*, _italic_")
    print("- Add inline_keyboard for approval buttons")
    print("- Messages are limited to 4096 characters")
