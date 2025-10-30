from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

class TelegramGetUpdates(BaseTool):
    """
    Polls Telegram Bot API for new messages and updates.
    Used to monitor for incoming voice messages from users.
    """

    offset: int = Field(
        default=0,
        description="Updates offset for long polling (use last update_id + 1)"
    )

    timeout: int = Field(
        default=30,
        description="Long polling timeout in seconds (0-50)"
    )

    limit: int = Field(
        default=100,
        description="Maximum number of updates to retrieve (1-100)"
    )

    def run(self):
        """
        Fetches updates from Telegram Bot API.
        Returns JSON string with new messages and updates.
        """
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            return json.dumps({
                "error": "TELEGRAM_BOT_TOKEN not found in environment variables"
            })

        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
            params = {
                "offset": self.offset,
                "timeout": self.timeout,
                "limit": self.limit
            }

            response = requests.get(url, params=params, timeout=self.timeout + 10)
            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                return json.dumps({
                    "error": f"Telegram API error: {data.get('description', 'Unknown error')}"
                })

            # Extract useful information
            updates = data.get("result", [])
            result = {
                "success": True,
                "update_count": len(updates),
                "updates": []
            }

            for update in updates:
                update_info = {
                    "update_id": update.get("update_id"),
                    "message": None,
                    "callback_query": None
                }

                if "message" in update:
                    msg = update["message"]
                    update_info["message"] = {
                        "message_id": msg.get("message_id"),
                        "chat_id": msg.get("chat", {}).get("id"),
                        "from_user": msg.get("from", {}).get("id"),
                        "username": msg.get("from", {}).get("username"),
                        "text": msg.get("text"),
                        "voice": msg.get("voice"),
                        "date": msg.get("date")
                    }

                if "callback_query" in update:
                    callback = update["callback_query"]
                    update_info["callback_query"] = {
                        "id": callback.get("id"),
                        "from_user": callback.get("from", {}).get("id"),
                        "message_id": callback.get("message", {}).get("message_id"),
                        "chat_id": callback.get("message", {}).get("chat", {}).get("id"),
                        "data": callback.get("data")
                    }

                result["updates"].append(update_info)

            # Add next offset suggestion
            if updates:
                result["next_offset"] = updates[-1]["update_id"] + 1

            return json.dumps(result, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"Failed to connect to Telegram API: {str(e)}"
            })
        except Exception as e:
            return json.dumps({
                "error": f"Error getting updates: {str(e)}"
            })


if __name__ == "__main__":
    print("Testing TelegramGetUpdates...")

    # Test 1: Check for token
    print("\n1. Check TELEGRAM_BOT_TOKEN:")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        print(f"Token found (starts with): {token[:10]}...")
    else:
        print("Warning: TELEGRAM_BOT_TOKEN not set")
        print("To test: Set TELEGRAM_BOT_TOKEN in .env file")

    # Test 2: Get updates (will fail without valid token)
    print("\n2. Test getUpdates call:")
    tool = TelegramGetUpdates(offset=0, timeout=1, limit=10)
    result = tool.run()
    print(result)

    # Test 3: With different parameters
    print("\n3. Test with custom offset:")
    tool = TelegramGetUpdates(offset=12345, timeout=2, limit=5)
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nUsage notes:")
    print("- Set TELEGRAM_BOT_TOKEN in .env to test with real bot")
    print("- Use offset from previous call to avoid duplicate messages")
    print("- Look for updates.message.voice to detect voice messages")
