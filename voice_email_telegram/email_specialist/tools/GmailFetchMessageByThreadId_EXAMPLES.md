# GmailFetchMessageByThreadId - Usage Examples

## Quick Reference

### Basic Usage
```python
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

# Fetch thread
tool = GmailFetchMessageByThreadId(thread_id="18c1234567890abcd")
result = tool.run()
```

## Real-World Scenarios

### Scenario 1: Show Full Conversation with Person

**User Request**: "Show me the full conversation with John Smith"

**Implementation**:
```python
import json
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

# Step 1: Find email from John
search_tool = GmailFetchEmails(
    query="from:john.smith@example.com",
    max_results=1
)
search_result = json.loads(search_tool.run())

if search_result["success"] and search_result["count"] > 0:
    # Step 2: Get thread_id from first email
    first_email = search_result["messages"][0]
    thread_id = first_email["threadId"]

    # Step 3: Fetch full conversation
    thread_tool = GmailFetchMessageByThreadId(thread_id=thread_id)
    thread_result = json.loads(thread_tool.run())

    if thread_result["success"]:
        print(f"Conversation with John ({thread_result['message_count']} messages):\n")

        for i, msg in enumerate(thread_result["messages"], 1):
            print(f"Message {i}:")
            print(f"  From: {msg['from']}")
            print(f"  Date: {msg['date']}")
            print(f"  Subject: {msg['subject']}")
            print(f"  {msg['snippet']}\n")
```

### Scenario 2: Read Entire Email Thread

**User Request**: "Read all messages in this thread"

**Implementation**:
```python
import json
import base64
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

# Assume we have thread_id from context
thread_id = "18cabcdef12345678"

tool = GmailFetchMessageByThreadId(thread_id=thread_id)
result = json.loads(tool.run())

if result["success"]:
    print(f"Thread contains {result['message_count']} messages\n")
    print("=" * 70)

    for i, msg in enumerate(result["messages"], 1):
        print(f"\nMessage {i}/{result['message_count']}")
        print(f"From: {msg['from']}")
        print(f"To: {msg['to']}")
        print(f"Date: {msg['date']}")
        print(f"Subject: {msg['subject']}")
        print("-" * 70)

        # Decode body content
        if msg["body_data"]:
            try:
                body = base64.b64decode(msg["body_data"]).decode('utf-8')
                print(body)
            except:
                print(msg["snippet"])  # Fallback to snippet
        else:
            print(msg["snippet"])

        print("=" * 70)
```

### Scenario 3: Project Email Exchange History

**User Request**: "What's the full email exchange about the Q4 project?"

**Implementation**:
```python
import json
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

# Step 1: Search for Q4 project emails
search_tool = GmailFetchEmails(
    query="subject:Q4 project",
    max_results=10
)
search_result = json.loads(search_tool.run())

if search_result["success"]:
    print(f"Found {search_result['count']} threads about Q4 project\n")

    # Step 2: Get full conversation for each thread
    for email in search_result["messages"]:
        thread_id = email["threadId"]

        thread_tool = GmailFetchMessageByThreadId(thread_id=thread_id)
        thread_result = json.loads(thread_tool.run())

        if thread_result["success"]:
            print(f"Thread: {email['subject']}")
            print(f"Messages: {thread_result['message_count']}")
            print(f"Participants:")

            # Extract unique participants
            participants = set()
            for msg in thread_result["messages"]:
                participants.add(msg["from"])

            for p in participants:
                print(f"  - {p}")
            print()
```

### Scenario 4: Unread Conversation Summary

**User Request**: "Summarize the unread conversation in my inbox"

**Implementation**:
```python
import json
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

# Step 1: Get unread emails
search_tool = GmailFetchEmails(
    query="is:unread",
    max_results=5
)
search_result = json.loads(search_tool.run())

if search_result["success"]:
    for email in search_result["messages"]:
        thread_id = email["threadId"]

        # Step 2: Get full thread for context
        thread_tool = GmailFetchMessageByThreadId(thread_id=thread_id)
        thread_result = json.loads(thread_tool.run())

        if thread_result["success"]:
            messages = thread_result["messages"]

            print(f"Conversation: {messages[0]['subject']}")
            print(f"Started: {messages[0]['date']}")
            print(f"Latest: {messages[-1]['date']}")
            print(f"Total messages: {len(messages)}")

            # Count unread
            unread = sum(1 for m in messages if "UNREAD" in m.get("labels", []))
            print(f"Unread: {unread}")

            # Show latest message snippet
            print(f"Latest message from: {messages[-1]['from']}")
            print(f"  {messages[-1]['snippet']}\n")
```

### Scenario 5: Meeting Thread History

**User Request**: "Show me the email thread about tomorrow's meeting"

**Implementation**:
```python
import json
from datetime import datetime, timedelta
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

# Step 1: Search for meeting emails from last week
tomorrow = datetime.now() + timedelta(days=1)
search_query = f"subject:meeting newer_than:7d"

search_tool = GmailFetchEmails(
    query=search_query,
    max_results=5
)
search_result = json.loads(search_tool.run())

if search_result["success"] and search_result["count"] > 0:
    # Get first matching thread
    thread_id = search_result["messages"][0]["threadId"]

    # Step 2: Fetch full thread
    thread_tool = GmailFetchMessageByThreadId(thread_id=thread_id)
    thread_result = json.loads(thread_tool.run())

    if thread_result["success"]:
        print("Meeting Email Thread History\n")
        print("=" * 70)

        for i, msg in enumerate(thread_result["messages"], 1):
            print(f"\n{i}. {msg['date']}")
            print(f"   From: {msg['from']}")

            # Extract key meeting info from snippet
            snippet = msg['snippet'].lower()
            if 'time:' in snippet or 'when:' in snippet or 'date:' in snippet:
                print(f"   📅 CONTAINS MEETING DETAILS")

            print(f"   {msg['snippet'][:100]}...")
```

## Advanced Usage

### Extract Thread Participants

```python
import json
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

def get_thread_participants(thread_id):
    """Extract all unique participants in a thread."""
    tool = GmailFetchMessageByThreadId(thread_id=thread_id)
    result = json.loads(tool.run())

    if result["success"]:
        participants = set()

        for msg in result["messages"]:
            # Add sender
            participants.add(msg["from"])

            # Add recipients
            if msg["to"]:
                for recipient in msg["to"].split(","):
                    participants.add(recipient.strip())

            # Add CC
            if msg["cc"]:
                for cc in msg["cc"].split(","):
                    participants.add(cc.strip())

        return list(participants)

    return []

# Usage
participants = get_thread_participants("18c1234567890abcd")
print("Thread participants:")
for p in participants:
    print(f"  - {p}")
```

### Thread Timeline Analysis

```python
import json
from datetime import datetime
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

def analyze_thread_timeline(thread_id):
    """Analyze the timeline of a conversation."""
    tool = GmailFetchMessageByThreadId(thread_id=thread_id)
    result = json.loads(tool.run())

    if result["success"]:
        messages = result["messages"]

        # Calculate conversation duration
        first_date = messages[0]["date"]
        last_date = messages[-1]["date"]

        print(f"Conversation Timeline:")
        print(f"  Started: {first_date}")
        print(f"  Latest: {last_date}")
        print(f"  Total messages: {len(messages)}")

        # Response pattern
        print("\n  Message flow:")
        for i, msg in enumerate(messages, 1):
            sender = msg["from"].split("<")[0].strip()
            print(f"    {i}. {sender} - {msg['date']}")

        return {
            "start_date": first_date,
            "end_date": last_date,
            "message_count": len(messages),
            "timeline": [(m["from"], m["date"]) for m in messages]
        }

    return None

# Usage
timeline = analyze_thread_timeline("18c1234567890abcd")
```

### Find Attachments in Thread

```python
import json
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

def find_thread_attachments(thread_id):
    """Find all messages with attachments in a thread."""
    tool = GmailFetchMessageByThreadId(thread_id=thread_id)
    result = json.loads(tool.run())

    if result["success"]:
        messages_with_attachments = []

        for msg in result["messages"]:
            # Check for attachment in raw data
            raw_data = msg.get("raw_data", {})
            payload = raw_data.get("payload", {})

            # Check if has attachments
            if payload.get("parts"):
                for part in payload["parts"]:
                    if part.get("filename"):
                        messages_with_attachments.append({
                            "message_id": msg["message_id"],
                            "from": msg["from"],
                            "date": msg["date"],
                            "filename": part["filename"],
                            "mime_type": part.get("mimeType")
                        })

        return messages_with_attachments

    return []

# Usage
attachments = find_thread_attachments("18c1234567890abcd")
print(f"Found {len(attachments)} messages with attachments")
for att in attachments:
    print(f"  - {att['filename']} from {att['from']}")
```

## Error Handling Patterns

### Robust Thread Fetching

```python
import json
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

def fetch_thread_safely(thread_id):
    """Fetch thread with comprehensive error handling."""
    if not thread_id:
        return {
            "success": False,
            "error": "No thread_id provided"
        }

    try:
        tool = GmailFetchMessageByThreadId(thread_id=thread_id)
        result = json.loads(tool.run())

        if result["success"]:
            return result
        else:
            # Handle specific errors
            error = result.get("error", "")

            if "credentials" in error.lower():
                print("❌ Authentication issue - check API keys")
            elif "not found" in error.lower():
                print("❌ Thread not found - may be deleted")
            elif "permission" in error.lower():
                print("❌ Access denied - check permissions")
            else:
                print(f"❌ Error: {error}")

            return result

    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }

# Usage
result = fetch_thread_safely("18c1234567890abcd")
if result["success"]:
    print(f"✅ Fetched {result['message_count']} messages")
else:
    print(f"❌ Failed: {result['error']}")
```

## Integration Examples

### With Voice Interface

```python
import json
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

def handle_voice_command(command):
    """Process voice command for thread operations."""

    # Parse command
    if "conversation with" in command.lower():
        # Extract sender name
        name = command.lower().split("conversation with")[1].strip()

        # Search for emails
        search_tool = GmailFetchEmails(
            query=f"from:{name}",
            max_results=1
        )
        search_result = json.loads(search_tool.run())

        if search_result["success"] and search_result["count"] > 0:
            thread_id = search_result["messages"][0]["threadId"]

            # Fetch thread
            thread_tool = GmailFetchMessageByThreadId(thread_id=thread_id)
            thread_result = json.loads(thread_tool.run())

            if thread_result["success"]:
                # Format for voice response
                msg_count = thread_result["message_count"]
                response = f"I found a conversation with {msg_count} messages. "

                latest = thread_result["messages"][-1]
                response += f"The latest message is from {latest['from']} "
                response += f"on {latest['date']}. "
                response += latest['snippet']

                return response

    return "I couldn't find that conversation."

# Usage
response = handle_voice_command("Show me the conversation with john smith")
print(response)
```

### With CEO Routing

```python
import json
from email_specialist.tools.GmailFetchMessageByThreadId import GmailFetchMessageByThreadId

def ceo_route_thread_request(user_intent, thread_id=None):
    """CEO routing logic for thread requests."""

    # Intent patterns
    thread_intents = [
        "show conversation",
        "full thread",
        "all messages",
        "email exchange",
        "conversation history"
    ]

    # Check if user wants thread
    wants_thread = any(intent in user_intent.lower() for intent in thread_intents)

    if wants_thread and thread_id:
        # Delegate to tool
        tool = GmailFetchMessageByThreadId(thread_id=thread_id)
        result = json.loads(tool.run())

        if result["success"]:
            # Format response for user
            return {
                "action": "show_thread",
                "thread_id": thread_id,
                "message_count": result["message_count"],
                "messages": result["messages"],
                "summary": f"Found {result['message_count']} messages in conversation"
            }
        else:
            return {
                "action": "error",
                "message": result["error"]
            }
    else:
        return {
            "action": "needs_thread_id",
            "message": "Please specify which conversation you'd like to see"
        }

# Usage
response = ceo_route_thread_request(
    "Show me the full conversation",
    thread_id="18c1234567890abcd"
)
print(response["summary"])
```

## Testing Tips

### 1. Get Real Thread IDs
```python
# First fetch some emails to get real thread IDs
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
import json

tool = GmailFetchEmails(max_results=5)
result = json.loads(tool.run())

if result["success"]:
    for email in result["messages"]:
        print(f"Thread ID: {email['threadId']}")
        print(f"Subject: {email.get('subject', 'No subject')}\n")
```

### 2. Test with Known Thread
```bash
python email_specialist/tools/test_gmail_fetch_thread.py 18c1234567890abcd
```

### 3. Compare with GmailGetMessage
```python
# Fetch thread
thread_result = json.loads(
    GmailFetchMessageByThreadId(thread_id="18c123...").run()
)

# Fetch individual message
message_result = json.loads(
    GmailGetMessage(message_id="18c123...").run()
)

# Compare
print("Thread has", thread_result["message_count"], "messages")
print("Individual fetch returned 1 message")
```

## Performance Tips

### 1. Cache Thread Data
```python
thread_cache = {}

def get_thread_cached(thread_id):
    if thread_id not in thread_cache:
        tool = GmailFetchMessageByThreadId(thread_id=thread_id)
        result = json.loads(tool.run())
        thread_cache[thread_id] = result

    return thread_cache[thread_id]
```

### 2. Limit Message Display
```python
# For long threads, show summary + recent messages
result = json.loads(tool.run())

if result["message_count"] > 10:
    print(f"Thread has {result['message_count']} messages")
    print("Showing 5 most recent:\n")

    recent_messages = result["messages"][-5:]
    for msg in recent_messages:
        print(f"- {msg['from']}: {msg['snippet']}")
```

### 3. Async Fetching (Future)
```python
# For multiple threads, could fetch in parallel
import asyncio

async def fetch_multiple_threads(thread_ids):
    # Future: Implement async version
    pass
```

---

**Last Updated**: 2025-11-01
**Tool Version**: 1.0.0
**Status**: ✅ Production Ready
