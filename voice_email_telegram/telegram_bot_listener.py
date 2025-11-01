#!/usr/bin/env python3
"""
Telegram Bot Listener for Voice Email System
Polls for Telegram messages and processes them through the agency
"""

import json
import os
import time
from datetime import datetime

from dotenv import load_dotenv

# Import agency
from agency import agency

# Import Telegram tools
from voice_handler.tools.TelegramGetUpdates import TelegramGetUpdates
from voice_handler.tools.TelegramSendMessage import TelegramSendMessage
from voice_handler.tools.TelegramDownloadFile import TelegramDownloadFile
from voice_handler.tools.ParseVoiceToText import ParseVoiceToText

load_dotenv()


class TelegramBotListener:
    """Listens for Telegram messages and processes them through the agency"""

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.offset = 0
        self.running = False

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not found in .env")

        print("=" * 80)
        print("TELEGRAM BOT LISTENER")
        print("=" * 80)
        print(f"Bot Token: {self.bot_token[:20]}...")
        print(f"Status: Initializing...")
        print("=" * 80)

    def send_telegram_message(self, chat_id: int, text: str):
        """Send a message back to the user via Telegram"""
        try:
            tool = TelegramSendMessage(chat_id=str(chat_id), text=text)
            result = tool.run()
            result_data = json.loads(result)

            if result_data.get("success"):
                print(f"✅ Sent reply to chat {chat_id}")
                return True
            else:
                print(f"❌ Failed to send: {result_data.get('error')}")
                return False

        except Exception as e:
            print(f"❌ Error sending message: {str(e)}")
            return False

    def process_voice_message(self, message_data: dict):
        """Process a voice message through the agency"""
        chat_id = message_data.get("chat_id")
        voice_data = message_data.get("voice")

        if not voice_data:
            return

        print(f"\n🎤 Voice message received from chat {chat_id}")

        try:
            # Step 1: Download voice file
            file_id = voice_data.get("file_id")
            download_tool = TelegramDownloadFile(file_id=file_id)
            download_result = json.loads(download_tool.run())

            if not download_result.get("success"):
                self.send_telegram_message(chat_id, "❌ Failed to download voice message")
                return

            file_path = download_result.get("local_path")
            print(f"📥 Downloaded: {file_path}")

            # Step 2: Convert voice to text
            transcribe_tool = ParseVoiceToText(audio_file_path=file_path)
            transcribe_result = json.loads(transcribe_tool.run())

            if transcribe_result.get("error"):
                self.send_telegram_message(chat_id, "❌ Failed to transcribe voice message")
                return

            transcript = transcribe_result.get("transcript")
            print(f"📝 Transcript: {transcript[:100]}...")

            # Step 3: Send to agency for processing
            self.send_telegram_message(
                chat_id, f"✅ Got it! Processing: \"{transcript[:50]}...\"\n\nDrafting your email..."
            )

            # Process through agency
            print(f"🤖 Processing through agency...")
            response = agency.get_completion(
                f"""User sent a voice message that was transcribed to:

"{transcript}"

Please process this voice message to extract email intent, draft an appropriate email,
and send it via Gmail. Provide a summary of what you did."""
            )

            print(f"✅ Agency response received")

            # Step 4: Send response back to user
            self.send_telegram_message(chat_id, f"✅ Email processed!\n\n{response}")

            print(f"✅ Complete workflow finished for chat {chat_id}")

        except Exception as e:
            print(f"❌ Error processing voice message: {str(e)}")
            self.send_telegram_message(chat_id, f"❌ Error processing your message: {str(e)}")

    def process_text_message(self, message_data: dict):
        """Process a text message through the agency"""
        chat_id = message_data.get("chat_id")
        text = message_data.get("text")

        if not text:
            return

        # Ignore bot commands for now
        if text.startswith("/"):
            if text == "/start":
                welcome = """👋 Welcome to Voice Email Assistant!

Send me a voice message describing the email you want to send, and I'll:
1. Transcribe your voice
2. Extract the email details
3. Draft a professional email
4. Send it via Gmail

Example: "Send an email to John about the meeting tomorrow at 2pm"

Ready when you are! 🎤"""
                self.send_telegram_message(chat_id, welcome)
            return

        print(f"\n📨 Text message received from chat {chat_id}: {text[:50]}...")

        try:
            self.send_telegram_message(chat_id, "✅ Processing your request...")

            # Process through agency
            response = agency.get_completion(
                f"""User sent a text message:

"{text}"

Please process this to extract email intent, draft an appropriate email,
and send it via Gmail. Provide a summary of what you did."""
            )

            # Send response back
            self.send_telegram_message(chat_id, f"✅ Email processed!\n\n{response}")

            print(f"✅ Complete workflow finished for chat {chat_id}")

        except Exception as e:
            print(f"❌ Error processing text message: {str(e)}")
            self.send_telegram_message(chat_id, f"❌ Error: {str(e)}")

    def process_updates(self, updates: list):
        """Process a batch of updates from Telegram"""
        for update in updates:
            message = update.get("message")

            if not message:
                continue

            # Check for voice message
            if message.get("voice"):
                self.process_voice_message(message)

            # Check for text message
            elif message.get("text"):
                self.process_text_message(message)

    def start(self):
        """Start listening for Telegram messages"""
        self.running = True

        print("\n" + "=" * 80)
        print("🚀 BOT LISTENER STARTED")
        print("=" * 80)
        print("Waiting for messages...")
        print("Press Ctrl+C to stop")
        print("=" * 80 + "\n")

        try:
            while self.running:
                try:
                    # Poll for updates
                    tool = TelegramGetUpdates(offset=self.offset, timeout=30, limit=10)

                    result = tool.run()
                    result_data = json.loads(result)

                    if result_data.get("error"):
                        print(f"⚠️ Error: {result_data.get('error')}")
                        time.sleep(5)
                        continue

                    updates = result_data.get("updates", [])

                    if updates:
                        print(f"\n📬 Received {len(updates)} update(s) at {datetime.now().strftime('%H:%M:%S')}")

                        # Process updates
                        self.process_updates(updates)

                        # Update offset
                        self.offset = result_data.get("next_offset", self.offset)

                        print(f"✅ Updates processed. Next offset: {self.offset}")
                    else:
                        # No updates - just continue polling
                        pass

                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    print(f"❌ Error in polling loop: {str(e)}")
                    time.sleep(5)

        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("🛑 STOPPING BOT LISTENER")
            print("=" * 80)
            self.running = False

    def stop(self):
        """Stop the listener"""
        self.running = False


if __name__ == "__main__":
    try:
        listener = TelegramBotListener()
        listener.start()
    except ValueError as e:
        print(f"❌ Configuration Error: {str(e)}")
        print("Please set TELEGRAM_BOT_TOKEN in your .env file")
    except Exception as e:
        print(f"❌ Fatal Error: {str(e)}")
        import traceback

        traceback.print_exc()
