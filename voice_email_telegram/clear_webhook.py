#!/usr/bin/env python3
"""Clear Telegram webhook to allow polling"""
import requests
import os
from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

# Check webhook status
response = requests.get(f"https://api.telegram.org/bot{bot_token}/getWebhookInfo")
print("Current webhook status:")
print(response.json())

# Delete webhook
print("\nDeleting webhook...")
response = requests.post(f"https://api.telegram.org/bot{bot_token}/deleteWebhook")
print(response.json())

# Verify deleted
response = requests.get(f"https://api.telegram.org/bot{bot_token}/getWebhookInfo")
print("\nWebhook status after delete:")
print(response.json())
