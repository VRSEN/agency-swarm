from agency_swarm.tools import BaseTool
from pydantic import Field
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

class TelegramDownloadFile(BaseTool):
    """
    Downloads a file from Telegram (voice messages, documents, etc.).
    First gets file path, then downloads the file to local storage.
    """

    file_id: str = Field(
        ...,
        description="Telegram file_id from a message (e.g., voice.file_id)"
    )

    save_path: str = Field(
        default="/tmp",
        description="Directory to save the downloaded file"
    )

    def run(self):
        """
        Downloads the file from Telegram.
        Returns JSON string with local file path.
        """
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not bot_token:
            return json.dumps({
                "error": "TELEGRAM_BOT_TOKEN not found in environment variables"
            })

        try:
            # Step 1: Get file path from Telegram
            get_file_url = f"https://api.telegram.org/bot{bot_token}/getFile"
            params = {"file_id": self.file_id}

            response = requests.get(get_file_url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            if not data.get("ok"):
                return json.dumps({
                    "error": f"Telegram API error: {data.get('description', 'Unknown error')}"
                })

            file_path = data["result"]["file_path"]
            file_size = data["result"].get("file_size", 0)

            # Step 2: Download the file
            download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"

            # Create save directory if it doesn't exist
            os.makedirs(self.save_path, exist_ok=True)

            # Generate local filename
            filename = os.path.basename(file_path)
            local_path = os.path.join(self.save_path, f"{self.file_id}_{filename}")

            # Download file
            file_response = requests.get(download_url, timeout=60)
            file_response.raise_for_status()

            # Save to disk
            with open(local_path, "wb") as f:
                f.write(file_response.content)

            result = {
                "success": True,
                "file_id": self.file_id,
                "local_path": local_path,
                "file_size": file_size,
                "telegram_path": file_path
            }

            return json.dumps(result, indent=2)

        except requests.exceptions.RequestException as e:
            return json.dumps({
                "error": f"Failed to download file: {str(e)}"
            })
        except Exception as e:
            return json.dumps({
                "error": f"Error downloading file: {str(e)}"
            })


if __name__ == "__main__":
    print("Testing TelegramDownloadFile...")

    # Test 1: Check for token
    print("\n1. Check TELEGRAM_BOT_TOKEN:")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        print(f"Token found (starts with): {token[:10]}...")
    else:
        print("Warning: TELEGRAM_BOT_TOKEN not set")

    # Test 2: Try to download (will fail without valid file_id)
    print("\n2. Test download with dummy file_id:")
    tool = TelegramDownloadFile(
        file_id="test_file_id_12345",
        save_path="/tmp/telegram_files"
    )
    result = tool.run()
    print(result)

    print("\nTest completed!")
    print("\nUsage notes:")
    print("- Get file_id from TelegramGetUpdates response")
    print("- Voice messages: updates[].message.voice.file_id")
    print("- Downloaded file path will be in the response")
    print("- Use downloaded file with ParseVoiceToText tool")
