# Telegram Integration Guide

Complete guide for integrating Telegram with your voice-first email system using Composio.

---

## Overview

Telegram will serve as the primary user interface for your voice-first email system. Users will:
- Request email drafts via Telegram messages
- Receive voice messages of draft emails
- Approve or modify drafts
- Get confirmation when emails are sent

---

## Authentication Options

### Option 1: Bot Token (Recommended)

**Best for**: Automated bots, public services, customer-facing applications

**Pros**:
- Simple setup
- No phone number required
- Works 24/7
- Can serve multiple users
- Official Telegram Bot API

**Cons**:
- Cannot access user chats (only bot chats)
- Cannot send messages to users who haven't started chat
- Limited to bot capabilities

### Option 2: API ID + Hash (User Account)

**Best for**: Personal automation, accessing your own messages

**Pros**:
- Full Telegram API access
- Can send messages to any contact
- Can read message history
- Access to channels and groups

**Cons**:
- Requires phone number
- Personal account access (security consideration)
- More complex setup
- Rate limits for non-bot usage

**For this project, use Option 1 (Bot Token).**

---

## Setting Up Telegram Bot

### Step 1: Create Bot via BotFather

1. **Open Telegram** (mobile or desktop app)

2. **Search for BotFather**
   - Username: `@BotFather`
   - Official bot with blue verification badge

3. **Start chat with BotFather**
   - Click "Start" or send `/start`

4. **Create new bot**
   - Send command: `/newbot`

5. **Choose bot name**
   - Example: "Voice Email Assistant"
   - This is the display name users see

6. **Choose username**
   - Must end in "bot"
   - Example: `voice_email_assistant_bot`
   - Must be unique across all Telegram

7. **Save bot token**
   - BotFather sends token like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`
   - **Important**: Save immediately, you can't retrieve it later
   - If lost, use `/token` command with BotFather

### Step 2: Configure Bot Settings

Send these commands to BotFather:

#### Set Description
```
/setdescription
# Select your bot
# Enter description:
```
Example description:
```
Voice-first email draft approval system.
I help you create, review, and send emails through voice messages.
```

#### Set About Text
```
/setabouttext
# Select your bot
# Enter text:
```
Example:
```
Voice Email Assistant - Create and approve emails with voice
```

#### Set Commands
```
/setcommands
# Select your bot
# Enter commands (one per line):
```
Example commands:
```
start - Start the bot
help - Show available commands
draft - Create new email draft
approve - Approve and send email
cancel - Cancel current draft
status - Check draft status
```

#### Set Profile Picture (Optional)
```
/setuserpic
# Select your bot
# Upload image (512x512 recommended)
```

### Step 3: Test Your Bot

1. Search for your bot in Telegram (by username)
2. Click "Start" button
3. Send `/help` command
4. Bot should respond (if webhook/polling configured)

---

## Connecting to Composio

### Method 1: Using Python

```python
from composio import Composio
import os

composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
entity_id = "default_user"

# Connect Telegram bot
connection = composio.connections.initiate(
    integration="TELEGRAM",
    entity_id=entity_id,
    auth_config={
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN")
    }
)

print(f"Connection status: {connection.status}")
```

### Method 2: Using CLI

```bash
# Set environment variable
export TELEGRAM_BOT_TOKEN="your-bot-token"

# Add connection
composio connections add TELEGRAM \
    --entity-id "default_user" \
    --auth-config '{"bot_token":"'$TELEGRAM_BOT_TOKEN'"}'
```

### Verify Connection

```python
from composio import Composio

composio = Composio()
connections = composio.connections.list(entity_id="default_user")

for conn in connections:
    if conn.integration == "TELEGRAM":
        print(f"Status: {conn.status}")
        print(f"Connected: {conn.created_at}")
```

---

## Available Composio Actions

### Sending Messages

#### 1. Send Text Message

```python
result = composio.tools.execute(
    action="TELEGRAM_SEND_MESSAGE",
    params={
        "chat_id": "123456789",  # User's Telegram ID
        "text": "Hello from Voice Email Assistant!",
        "parse_mode": "Markdown"  # or "HTML"
    },
    entity_id="default_user"
)
```

#### 2. Send Voice Message

```python
result = composio.tools.execute(
    action="TELEGRAM_SEND_VOICE",
    params={
        "chat_id": "123456789",
        "voice": "path/to/voice.ogg",  # or file_id or URL
        "caption": "Your email draft",
        "duration": 30  # seconds
    },
    entity_id="default_user"
)
```

#### 3. Send Document/File

```python
result = composio.tools.execute(
    action="TELEGRAM_SEND_DOCUMENT",
    params={
        "chat_id": "123456789",
        "document": "path/to/document.pdf",
        "caption": "Email attachment preview"
    },
    entity_id="default_user"
)
```

### Receiving Messages

#### 4. Get Updates

```python
result = composio.tools.execute(
    action="TELEGRAM_GET_UPDATES",
    params={
        "offset": 0,  # Update ID to start from
        "limit": 100,  # Max number of updates
        "timeout": 30  # Long polling timeout
    },
    entity_id="default_user"
)

# Process updates
for update in result['result']:
    if 'message' in update:
        message = update['message']
        chat_id = message['chat']['id']
        text = message.get('text', '')
        print(f"Received from {chat_id}: {text}")
```

#### 5. Handle Commands

```python
def handle_telegram_update(update):
    message = update.get('message', {})
    text = message.get('text', '')
    chat_id = message['chat']['id']

    if text == '/start':
        return send_welcome(chat_id)
    elif text == '/draft':
        return create_draft_interactive(chat_id)
    elif text == '/approve':
        return approve_draft(chat_id)
    elif text == '/cancel':
        return cancel_draft(chat_id)
```

### Interactive Features

#### 6. Send Keyboard (Buttons)

```python
result = composio.tools.execute(
    action="TELEGRAM_SEND_MESSAGE",
    params={
        "chat_id": "123456789",
        "text": "Choose an action:",
        "reply_markup": {
            "keyboard": [
                [{"text": "Create Draft"}, {"text": "View Drafts"}],
                [{"text": "Send Email"}, {"text": "Cancel"}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
    },
    entity_id="default_user"
)
```

#### 7. Send Inline Keyboard

```python
result = composio.tools.execute(
    action="TELEGRAM_SEND_MESSAGE",
    params={
        "chat_id": "123456789",
        "text": "Draft ready. What would you like to do?",
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "✓ Approve", "callback_data": "approve"},
                    {"text": "✗ Reject", "callback_data": "reject"}
                ],
                [
                    {"text": "✎ Edit", "callback_data": "edit"}
                ]
            ]
        }
    },
    entity_id="default_user"
)
```

#### 8. Handle Callback Queries

```python
def handle_callback_query(update):
    callback = update.get('callback_query', {})
    data = callback.get('data', '')
    message = callback.get('message', {})
    chat_id = message['chat']['id']

    if data == 'approve':
        send_email_and_notify(chat_id)
    elif data == 'reject':
        delete_draft_and_notify(chat_id)
    elif data == 'edit':
        start_edit_mode(chat_id)

    # Answer callback to remove loading state
    composio.tools.execute(
        action="TELEGRAM_ANSWER_CALLBACK_QUERY",
        params={
            "callback_query_id": callback['id'],
            "text": "Processing..."
        },
        entity_id="default_user"
    )
```

---

## Integration with Agency Swarm

### Create Telegram Agent

```python
from agency_swarm import Agent
from composio import Composio

composio = Composio()
entity_id = "default_user"

# Get Telegram tools
telegram_tools = composio.tools.get(
    toolkits=["TELEGRAM"],
    entity_id=entity_id
)

# Create agent
telegram_agent = Agent(
    name="TelegramAgent",
    description="Handles Telegram messaging interface",
    instructions="""
    You are the Telegram interface agent for a voice-first email system.

    Your responsibilities:
    1. Listen for incoming messages from users
    2. Parse user commands (/draft, /approve, /cancel)
    3. Send text and voice messages to users
    4. Present interactive keyboards for user choices
    5. Handle callback queries from inline buttons
    6. Coordinate with EmailAgent for email operations
    7. Coordinate with VoiceAgent for voice synthesis

    Message format guidelines:
    - Use Markdown for formatting
    - Keep messages concise and clear
    - Always confirm actions before execution
    - Provide helpful error messages

    Commands to handle:
    - /start: Welcome message and instructions
    - /draft: Start email draft creation
    - /approve: Approve current draft and send
    - /cancel: Cancel current draft
    - /help: Show available commands
    - /status: Show current draft status
    """,
    tools=telegram_tools
)
```

### Implement Message Polling

```python
import time

class TelegramPoller:
    def __init__(self, composio, entity_id, handlers):
        self.composio = composio
        self.entity_id = entity_id
        self.handlers = handlers
        self.last_update_id = 0

    def poll(self):
        """Poll for new messages"""
        result = self.composio.tools.execute(
            action="TELEGRAM_GET_UPDATES",
            params={
                "offset": self.last_update_id + 1,
                "timeout": 30
            },
            entity_id=self.entity_id
        )

        updates = result.get('result', [])

        for update in updates:
            self.last_update_id = update['update_id']
            self.handle_update(update)

    def handle_update(self, update):
        """Route update to appropriate handler"""
        if 'message' in update:
            self.handlers['message'](update['message'])
        elif 'callback_query' in update:
            self.handlers['callback'](update['callback_query'])

    def start(self):
        """Start polling loop"""
        print("Starting Telegram poller...")
        while True:
            try:
                self.poll()
            except Exception as e:
                print(f"Polling error: {e}")
                time.sleep(5)

# Usage
def handle_message(message):
    chat_id = message['chat']['id']
    text = message.get('text', '')
    print(f"Received: {text} from {chat_id}")
    # Process with agency

def handle_callback(callback):
    data = callback['data']
    print(f"Callback: {data}")
    # Process with agency

poller = TelegramPoller(
    composio=composio,
    entity_id="default_user",
    handlers={
        'message': handle_message,
        'callback': handle_callback
    }
)

# Run in background thread
import threading
polling_thread = threading.Thread(target=poller.start, daemon=True)
polling_thread.start()
```

---

## Webhook Setup (Production)

For production, use webhooks instead of polling:

### 1. Set Webhook URL

```python
import os

# Your server's public URL
webhook_url = "https://your-server.com/telegram-webhook"

result = composio.tools.execute(
    action="TELEGRAM_SET_WEBHOOK",
    params={
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"]
    },
    entity_id="default_user"
)
```

### 2. Create Webhook Endpoint

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    update = request.get_json()

    # Process update
    if 'message' in update:
        handle_message(update['message'])
    elif 'callback_query' in update:
        handle_callback(update['callback_query'])

    return jsonify({"ok": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8443)
```

### 3. Secure with HTTPS

Telegram requires HTTPS for webhooks:

```bash
# Option 1: Use Let's Encrypt
certbot certonly --standalone -d your-server.com

# Option 2: Use ngrok for testing
ngrok http 8443
# Use ngrok HTTPS URL as webhook
```

---

## Best Practices

### 1. Rate Limiting

```python
from time import sleep

def send_message_with_rate_limit(chat_id, text):
    """Send message with rate limiting"""
    try:
        result = composio.tools.execute(
            action="TELEGRAM_SEND_MESSAGE",
            params={"chat_id": chat_id, "text": text},
            entity_id="default_user"
        )
        sleep(0.05)  # 50ms delay between messages
        return result
    except Exception as e:
        if "429" in str(e):  # Too Many Requests
            sleep(1)
            return send_message_with_rate_limit(chat_id, text)
        raise
```

### 2. Error Handling

```python
def safe_send_message(chat_id, text):
    """Send message with error handling"""
    try:
        return composio.tools.execute(
            action="TELEGRAM_SEND_MESSAGE",
            params={"chat_id": chat_id, "text": text},
            entity_id="default_user"
        )
    except Exception as e:
        error_msg = str(e)
        if "bot was blocked" in error_msg:
            print(f"User {chat_id} blocked the bot")
        elif "chat not found" in error_msg:
            print(f"Chat {chat_id} not found")
        else:
            print(f"Error sending message: {e}")
        return None
```

### 3. User State Management

```python
class UserSession:
    def __init__(self):
        self.sessions = {}

    def get(self, chat_id):
        if chat_id not in self.sessions:
            self.sessions[chat_id] = {
                "state": "idle",
                "draft": None,
                "context": {}
            }
        return self.sessions[chat_id]

    def update(self, chat_id, **kwargs):
        session = self.get(chat_id)
        session.update(kwargs)

# Usage
sessions = UserSession()

def handle_message(message):
    chat_id = message['chat']['id']
    text = message.get('text', '')
    session = sessions.get(chat_id)

    if session['state'] == 'idle':
        if text == '/draft':
            sessions.update(chat_id, state='draft_recipient')
            send_message(chat_id, "Who should receive the email?")
    elif session['state'] == 'draft_recipient':
        sessions.update(chat_id,
            state='draft_subject',
            context={'recipient': text}
        )
        send_message(chat_id, "What's the subject?")
    # ... continue workflow
```

### 4. Message Formatting

```python
def format_draft_preview(draft):
    """Format email draft for Telegram"""
    return f"""
📧 **Email Draft Preview**

**To:** {draft['to']}
**Subject:** {draft['subject']}

**Message:**
{draft['body']}

─────────────────
Use buttons below to approve or edit.
"""

def send_draft_preview(chat_id, draft):
    composio.tools.execute(
        action="TELEGRAM_SEND_MESSAGE",
        params={
            "chat_id": chat_id,
            "text": format_draft_preview(draft),
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "✓ Approve & Send", "callback_data": "approve"},
                        {"text": "✎ Edit", "callback_data": "edit"}
                    ],
                    [{"text": "✗ Cancel", "callback_data": "cancel"}]
                ]
            }
        },
        entity_id="default_user"
    )
```

---

## MCP Server Alternative

If you prefer using MCP servers instead of Composio:

### Install Telegram MCP Server

```bash
# Option 1: chigwell/telegram-mcp (recommended)
npm install telegram-mcp

# Option 2: Muhammad18557/telegram-mcp
git clone https://github.com/Muhammad18557/telegram-mcp
cd telegram-mcp
npm install
```

### Configure MCP Server

```json
{
  "telegram": {
    "command": "node",
    "args": ["/path/to/telegram-mcp/dist/index.js"],
    "env": {
      "TELEGRAM_API_ID": "your_api_id",
      "TELEGRAM_API_HASH": "your_api_hash",
      "TELEGRAM_BOT_TOKEN": "your_bot_token"
    }
  }
}
```

### Use with Agency Swarm

```python
# MCP tools would be auto-discovered
# Similar usage to Composio tools
```

---

## Troubleshooting

### Bot Not Responding

1. **Check token is correct**
   ```python
   # Test with getMe
   result = composio.tools.execute(
       action="TELEGRAM_GET_ME",
       params={},
       entity_id="default_user"
   )
   print(result)
   ```

2. **Verify webhook is not set** (if using polling)
   ```python
   # Delete webhook
   composio.tools.execute(
       action="TELEGRAM_DELETE_WEBHOOK",
       params={},
       entity_id="default_user"
   )
   ```

3. **Check for errors in updates**
   ```python
   updates = composio.tools.execute(
       action="TELEGRAM_GET_UPDATES",
       params={},
       entity_id="default_user"
   )
   print(updates)
   ```

### User Can't Find Bot

1. Verify username is correct
2. Check bot is not blocked by Telegram
3. Ensure username ends in "bot"
4. Search by exact username in Telegram

### Messages Not Sending

1. Check chat_id is correct
2. Verify user has started chat with bot
3. Check for rate limiting (429 errors)
4. Ensure bot isn't blocked by user

---

## Security Considerations

1. **Never expose bot token**
   ```python
   # Bad
   bot_token = "123456:ABC..."

   # Good
   bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
   ```

2. **Validate user input**
   ```python
   def sanitize_input(text):
       # Remove dangerous characters
       return text.replace('<', '').replace('>', '')
   ```

3. **Implement user whitelist** (optional)
   ```python
   ALLOWED_USERS = [123456789, 987654321]

   def is_authorized(chat_id):
       return chat_id in ALLOWED_USERS
   ```

4. **Rate limit requests**
   ```python
   from collections import defaultdict
   import time

   request_times = defaultdict(list)

   def check_rate_limit(chat_id, limit=10, window=60):
       now = time.time()
       request_times[chat_id] = [
           t for t in request_times[chat_id]
           if now - t < window
       ]

       if len(request_times[chat_id]) >= limit:
           return False

       request_times[chat_id].append(now)
       return True
   ```

---

## Resources

- Telegram Bot API: https://core.telegram.org/bots/api
- BotFather Commands: https://core.telegram.org/bots#botfather
- Composio Telegram Docs: https://docs.composio.dev/toolkits/telegram
- Bot Best Practices: https://core.telegram.org/bots/faq

---

## Next Steps

1. Test bot with simple echo functionality
2. Implement command handlers
3. Add inline keyboards for approval workflow
4. Integrate with email and voice agents
5. Deploy with webhooks for production
