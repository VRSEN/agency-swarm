# Mem0 Integration Guide

Complete guide for integrating Mem0 persistent memory with your voice-first email system.

---

## Overview

Mem0 provides long-term memory for your AI agents, enabling:
- Remember user preferences (email signature, default recipients)
- Store conversation context across sessions
- Learn from past email drafts
- Maintain user-specific settings
- Personalize responses based on history

---

## What is Mem0?

Mem0 is an AI memory layer that allows your agents to:
- **Store memories**: Save important information from conversations
- **Retrieve context**: Access relevant memories when needed
- **Update knowledge**: Modify existing memories
- **Organize information**: Categorize and search memories
- **Persist across sessions**: Maintain continuity between interactions

**Use Cases for Email System**:
- Remember user's email signature
- Store frequently used email templates
- Remember recipient preferences
- Track email history and patterns
- Learn user's writing style

---

## Getting Your API Key

### Step 1: Sign Up for Mem0

1. **Visit Mem0 Platform**
   - Go to https://mem0.ai
   - Click "Get Started" or "Sign Up"

2. **Create Account**
   - Use email sign-up
   - Or sign in with Google/GitHub

3. **Verify Email**
   - Check inbox for verification
   - Click verification link

### Step 2: Get API Key

1. **Navigate to Dashboard**
   - Log in to https://app.mem0.ai
   - Go to dashboard home

2. **Find API Keys Section**
   - Look for "API Keys" or "Settings"
   - Click on "API Keys" tab

3. **Generate API Key**
   - Click "Create API Key" or "New Key"
   - Name it: "Voice Email System"
   - Copy the key

4. **Save Securely**
   ```bash
   # Add to .env file
   echo "MEM0_API_KEY=your_mem0_key_here" >> .env
   ```

### Pricing Information

**Free Tier**:
- Check Mem0 website for current limits
- Usually includes basic memory operations
- Good for testing and small projects

**Paid Plans**:
- Varies based on usage
- Check https://mem0.ai/pricing for details

---

## Connecting to Composio

### Python Setup

```python
from composio import Composio
import os
from dotenv import load_dotenv

load_dotenv()

composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
entity_id = "default_user"

# Connect Mem0
connection = composio.connections.initiate(
    integration="MEM0",
    entity_id=entity_id,
    auth_config={
        "api_key": os.getenv("MEM0_API_KEY")
    }
)

print(f"Connection status: {connection.status}")
```

### Verify Connection

```python
# Check connection status
connections = composio.connections.list(entity_id="default_user")

for conn in connections:
    if conn.integration == "MEM0":
        print(f"Mem0: {conn.status}")
```

---

## Core Memory Operations

### 1. Add Memory

```python
result = composio.tools.execute(
    action="MEM0_ADD_MEMORY",
    params={
        "user_id": "telegram_123456",  # Unique user identifier
        "memory": "User prefers professional email signatures with title",
        "metadata": {
            "category": "preferences",
            "type": "email_signature",
            "timestamp": "2025-01-15"
        }
    },
    entity_id="default_user"
)

memory_id = result.get('memory_id')
print(f"Memory stored: {memory_id}")
```

### 2. Retrieve Memories

```python
result = composio.tools.execute(
    action="MEM0_GET_MEMORIES",
    params={
        "user_id": "telegram_123456",
        "limit": 10  # Number of memories to retrieve
    },
    entity_id="default_user"
)

memories = result.get('memories', [])
for memory in memories:
    print(f"Memory: {memory['text']}")
    print(f"ID: {memory['id']}")
    print(f"Created: {memory['created_at']}")
    print("---")
```

### 3. Search Memories

```python
result = composio.tools.execute(
    action="MEM0_SEARCH_MEMORIES",
    params={
        "user_id": "telegram_123456",
        "query": "email signature",  # Search query
        "limit": 5
    },
    entity_id="default_user"
)

matches = result.get('results', [])
for match in matches:
    print(f"Match: {match['text']}")
    print(f"Relevance: {match['score']}")
```

### 4. Update Memory

```python
result = composio.tools.execute(
    action="MEM0_UPDATE_MEMORY",
    params={
        "memory_id": "mem_123abc",
        "memory": "Updated: User prefers professional signatures with title and phone",
        "metadata": {
            "category": "preferences",
            "last_updated": "2025-01-20"
        }
    },
    entity_id="default_user"
)

print("Memory updated")
```

### 5. Delete Memory

```python
result = composio.tools.execute(
    action="MEM0_DELETE_MEMORY",
    params={
        "memory_id": "mem_123abc"
    },
    entity_id="default_user"
)

print("Memory deleted")
```

---

## Email System Memory Patterns

### User Preferences Manager

```python
class UserPreferences:
    def __init__(self, composio, entity_id):
        self.composio = composio
        self.entity_id = entity_id

    def save_preference(self, user_id, category, key, value):
        """Save user preference"""

        memory_text = f"{category}:{key}={value}"

        result = self.composio.tools.execute(
            action="MEM0_ADD_MEMORY",
            params={
                "user_id": user_id,
                "memory": memory_text,
                "metadata": {
                    "category": category,
                    "preference_key": key
                }
            },
            entity_id=self.entity_id
        )

        return result.get('memory_id')

    def get_preference(self, user_id, category, key):
        """Get user preference"""

        # Search for specific preference
        result = self.composio.tools.execute(
            action="MEM0_SEARCH_MEMORIES",
            params={
                "user_id": user_id,
                "query": f"{category} {key}",
                "limit": 1
            },
            entity_id=self.entity_id
        )

        matches = result.get('results', [])
        if matches:
            # Parse value from memory text
            memory_text = matches[0]['text']
            if '=' in memory_text:
                return memory_text.split('=', 1)[1]

        return None

    def get_all_preferences(self, user_id):
        """Get all user preferences"""

        result = self.composio.tools.execute(
            action="MEM0_GET_MEMORIES",
            params={
                "user_id": user_id,
                "limit": 100
            },
            entity_id=self.entity_id
        )

        preferences = {}
        for memory in result.get('memories', []):
            metadata = memory.get('metadata', {})
            if metadata.get('category') == 'preference':
                key = metadata.get('preference_key')
                value = memory['text'].split('=', 1)[1] if '=' in memory['text'] else None
                if key and value:
                    preferences[key] = value

        return preferences

# Usage
prefs = UserPreferences(composio, "default_user")

# Save preferences
prefs.save_preference(
    user_id="telegram_123456",
    category="email",
    key="signature",
    value="Best regards,\\nJohn Doe\\nSenior Developer"
)

prefs.save_preference(
    user_id="telegram_123456",
    category="email",
    key="default_recipient",
    value="team@example.com"
)

# Get preference
signature = prefs.get_preference("telegram_123456", "email", "signature")
print(f"Signature: {signature}")

# Get all preferences
all_prefs = prefs.get_all_preferences("telegram_123456")
print(f"All preferences: {all_prefs}")
```

### Email History Tracker

```python
class EmailHistoryTracker:
    def __init__(self, composio, entity_id):
        self.composio = composio
        self.entity_id = entity_id

    def save_email(self, user_id, email_data):
        """Save email to history"""

        memory_text = f"Sent email to {email_data['to']} about: {email_data['subject']}"

        result = self.composio.tools.execute(
            action="MEM0_ADD_MEMORY",
            params={
                "user_id": user_id,
                "memory": memory_text,
                "metadata": {
                    "category": "email_history",
                    "recipient": email_data['to'],
                    "subject": email_data['subject'],
                    "sent_at": email_data.get('sent_at', 'unknown')
                }
            },
            entity_id=self.entity_id
        )

        return result.get('memory_id')

    def get_emails_to_recipient(self, user_id, recipient):
        """Get email history with specific recipient"""

        result = self.composio.tools.execute(
            action="MEM0_SEARCH_MEMORIES",
            params={
                "user_id": user_id,
                "query": f"email to {recipient}",
                "limit": 10
            },
            entity_id=self.entity_id
        )

        return result.get('results', [])

    def get_recent_emails(self, user_id, limit=5):
        """Get recent email history"""

        result = self.composio.tools.execute(
            action="MEM0_GET_MEMORIES",
            params={
                "user_id": user_id,
                "limit": limit
            },
            entity_id=self.entity_id
        )

        # Filter for email history
        emails = []
        for memory in result.get('memories', []):
            if memory.get('metadata', {}).get('category') == 'email_history':
                emails.append(memory)

        return emails

# Usage
history = EmailHistoryTracker(composio, "default_user")

# Save sent email
history.save_email(
    user_id="telegram_123456",
    email_data={
        "to": "john@example.com",
        "subject": "Project Update",
        "sent_at": "2025-01-20T10:30:00"
    }
)

# Get emails to specific recipient
emails_to_john = history.get_emails_to_recipient("telegram_123456", "john@example.com")
print(f"Found {len(emails_to_john)} emails to John")

# Get recent emails
recent = history.get_recent_emails("telegram_123456", limit=5)
for email in recent:
    print(email['text'])
```

### Context-Aware Email Generator

```python
class ContextAwareEmailGenerator:
    def __init__(self, composio, entity_id):
        self.composio = composio
        self.entity_id = entity_id

    def generate_personalized_email(self, user_id, recipient, topic):
        """Generate email using stored context"""

        # Get relevant memories
        memories = self._get_relevant_context(user_id, recipient, topic)

        # Extract useful information
        context = {
            "signature": self._find_signature(memories),
            "past_emails": self._find_past_emails(memories, recipient),
            "preferences": self._find_preferences(memories)
        }

        # Generate email with context
        email_draft = self._compose_with_context(
            recipient=recipient,
            topic=topic,
            context=context
        )

        return email_draft

    def _get_relevant_context(self, user_id, recipient, topic):
        """Get relevant memories for email composition"""

        # Search for recipient-specific memories
        result = self.composio.tools.execute(
            action="MEM0_SEARCH_MEMORIES",
            params={
                "user_id": user_id,
                "query": f"{recipient} {topic}",
                "limit": 10
            },
            entity_id=self.entity_id
        )

        return result.get('results', [])

    def _find_signature(self, memories):
        """Extract signature from memories"""
        for memory in memories:
            if 'signature' in memory['text'].lower():
                # Extract signature
                return memory['text'].split('=', 1)[1] if '=' in memory['text'] else None
        return "Best regards"

    def _find_past_emails(self, memories, recipient):
        """Find past emails with recipient"""
        past_emails = []
        for memory in memories:
            if recipient in memory['text'] and 'email' in memory['text'].lower():
                past_emails.append(memory)
        return past_emails

    def _find_preferences(self, memories):
        """Extract preferences"""
        preferences = {}
        for memory in memories:
            if 'preference' in memory.get('metadata', {}).get('category', ''):
                # Parse preference
                key = memory.get('metadata', {}).get('preference_key')
                if key:
                    preferences[key] = memory['text']
        return preferences

    def _compose_with_context(self, recipient, topic, context):
        """Compose email using context"""

        # Check if we've emailed this recipient before
        is_follow_up = len(context['past_emails']) > 0

        # Build email
        greeting = "Hi" if is_follow_up else "Dear"

        email = {
            "to": recipient,
            "subject": topic,
            "body": f"""{greeting},

{topic}

[Email body will be generated here based on context]

{context['signature']}
"""
        }

        return email

# Usage
generator = ContextAwareEmailGenerator(composio, "default_user")

email = generator.generate_personalized_email(
    user_id="telegram_123456",
    recipient="john@example.com",
    topic="Following up on our meeting"
)

print(email)
```

---

## Integration with Agency Swarm

### Create Memory Agent

```python
from agency_swarm import Agent
from composio import Composio

composio = Composio()
entity_id = "default_user"

# Get Mem0 tools
mem0_tools = composio.tools.get(
    toolkits=["MEM0"],
    entity_id=entity_id
)

# Create agent
memory_agent = Agent(
    name="MemoryAgent",
    description="Manages persistent memory and user context",
    instructions="""
    You are the memory management agent for a voice-first email system.

    Your responsibilities:
    1. Store user preferences and settings
    2. Remember email history and patterns
    3. Retrieve relevant context for email composition
    4. Learn from user interactions
    5. Maintain personalization across sessions

    What to Remember:
    - User's email signature
    - Frequently contacted recipients
    - Email templates and patterns
    - User's writing style preferences
    - Past email topics and subjects
    - User corrections and feedback
    - Scheduling preferences

    What NOT to Remember:
    - Sensitive personal information (unless explicitly requested)
    - Temporary/one-time information
    - System errors or failures

    Memory Organization:
    - Use clear, descriptive memory text
    - Add relevant metadata for filtering
    - Update memories when information changes
    - Delete outdated memories

    Retrieval Strategy:
    - Search for relevant memories before composing emails
    - Prioritize recent memories
    - Consider recipient context
    - Apply learned preferences automatically
    """,
    tools=mem0_tools
)
```

### Enhanced Agency with Memory

```python
from agency_swarm import Agency

# Create agency with memory agent
agency = Agency(
    agents=[
        memory_agent,
        telegram_agent,
        email_agent,
        voice_agent,
        [telegram_agent, memory_agent],  # Telegram can query memory
        [email_agent, memory_agent],     # Email uses memory for context
        [memory_agent, email_agent],     # Memory learns from emails
    ],
    shared_instructions="""
    You are a voice-first email system with persistent memory.

    Memory Usage:
    1. Before creating emails, check memory for:
       - User's signature
       - Past emails to this recipient
       - User preferences
    2. After sending emails, store:
       - Email summary
       - Recipient information
       - Any user feedback
    3. Learn from corrections:
       - If user edits draft, remember the change
       - Apply learned patterns to future emails

    Workflow with Memory:
    1. User requests email via Telegram
    2. MemoryAgent retrieves relevant context
    3. EmailAgent composes with context
    4. VoiceAgent reads draft
    5. TelegramAgent sends for approval
    6. If approved: Send and save to memory
    7. If edited: Learn from changes and save
    """,
    temperature=0.5,
    max_prompt_tokens=4000
)
```

---

## Advanced Patterns

### Learning from User Feedback

```python
class FeedbackLearner:
    def __init__(self, composio, entity_id):
        self.composio = composio
        self.entity_id = entity_id

    def learn_from_edit(self, user_id, original_draft, edited_draft):
        """Learn from user's edits"""

        # Identify what changed
        changes = self._identify_changes(original_draft, edited_draft)

        # Store learning
        for change_type, change_data in changes.items():
            memory_text = f"User preference: {change_type} - {change_data}"

            self.composio.tools.execute(
                action="MEM0_ADD_MEMORY",
                params={
                    "user_id": user_id,
                    "memory": memory_text,
                    "metadata": {
                        "category": "learning",
                        "change_type": change_type,
                        "learned_from": "user_edit"
                    }
                },
                entity_id=self.entity_id
            )

    def _identify_changes(self, original, edited):
        """Identify what changed between drafts"""
        changes = {}

        # Check subject changes
        if original['subject'] != edited['subject']:
            changes['subject_style'] = f"Changed '{original['subject']}' to '{edited['subject']}'"

        # Check body changes
        if original['body'] != edited['body']:
            # Analyze tone, length, etc.
            if len(edited['body']) < len(original['body']) * 0.8:
                changes['length_preference'] = "prefers shorter emails"
            elif len(edited['body']) > len(original['body']) * 1.2:
                changes['length_preference'] = "prefers longer, detailed emails"

        return changes

# Usage
learner = FeedbackLearner(composio, "default_user")

original = {
    "subject": "Quick Update",
    "body": "Hi,\n\nJust wanted to update you...\n\nBest"
}

edited = {
    "subject": "Project Status Update",
    "body": "Hi,\n\nQuick update on the project...\n\nBest regards"
}

learner.learn_from_edit("telegram_123456", original, edited)
```

### Conversation Context Tracking

```python
class ConversationTracker:
    def __init__(self, composio, entity_id):
        self.composio = composio
        self.entity_id = entity_id

    def track_conversation(self, user_id, message_type, content):
        """Track conversation flow"""

        memory_text = f"Conversation: {message_type} - {content}"

        self.composio.tools.execute(
            action="MEM0_ADD_MEMORY",
            params={
                "user_id": user_id,
                "memory": memory_text,
                "metadata": {
                    "category": "conversation",
                    "message_type": message_type,
                    "timestamp": datetime.now().isoformat()
                }
            },
            entity_id=self.entity_id
        )

    def get_conversation_context(self, user_id, limit=10):
        """Get recent conversation context"""

        result = self.composio.tools.execute(
            action="MEM0_GET_MEMORIES",
            params={
                "user_id": user_id,
                "limit": limit
            },
            entity_id=self.entity_id
        )

        # Filter for conversation memories
        conversation = []
        for memory in result.get('memories', []):
            if memory.get('metadata', {}).get('category') == 'conversation':
                conversation.append(memory['text'])

        return conversation

# Usage
tracker = ConversationTracker(composio, "default_user")

# Track user request
tracker.track_conversation(
    "telegram_123456",
    "user_request",
    "Create email to john@example.com about meeting"
)

# Track system response
tracker.track_conversation(
    "telegram_123456",
    "system_response",
    "Draft created and sent for approval"
)

# Get context
context = tracker.get_conversation_context("telegram_123456", limit=5)
print("Recent conversation:", context)
```

---

## Best Practices

### 1. Memory Organization

```python
# Use clear categories
MEMORY_CATEGORIES = {
    "preference": "User preferences and settings",
    "history": "Email history",
    "learning": "Learned patterns from user behavior",
    "conversation": "Conversation context",
    "template": "Saved email templates"
}

# Add metadata consistently
def add_categorized_memory(user_id, category, text, **extra_metadata):
    metadata = {
        "category": category,
        "created_at": datetime.now().isoformat(),
        **extra_metadata
    }

    composio.tools.execute(
        action="MEM0_ADD_MEMORY",
        params={
            "user_id": user_id,
            "memory": text,
            "metadata": metadata
        },
        entity_id="default_user"
    )
```

### 2. Memory Cleanup

```python
def cleanup_old_memories(user_id, days=30):
    """Remove memories older than specified days"""

    # Get all memories
    result = composio.tools.execute(
        action="MEM0_GET_MEMORIES",
        params={"user_id": user_id, "limit": 1000},
        entity_id="default_user"
    )

    cutoff_date = datetime.now() - timedelta(days=days)

    for memory in result.get('memories', []):
        created_at = memory.get('created_at')
        if created_at:
            created_date = datetime.fromisoformat(created_at)
            if created_date < cutoff_date:
                # Delete old memory
                composio.tools.execute(
                    action="MEM0_DELETE_MEMORY",
                    params={"memory_id": memory['id']},
                    entity_id="default_user"
                )
                print(f"Deleted old memory: {memory['id']}")
```

### 3. Privacy and Security

```python
# Redact sensitive information
def sanitize_memory(text):
    """Remove sensitive data before storing"""
    import re

    # Remove credit card numbers
    text = re.sub(r'\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}', '[REDACTED]', text)

    # Remove SSN
    text = re.sub(r'\d{3}-\d{2}-\d{4}', '[REDACTED]', text)

    # Remove phone numbers
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[REDACTED]', text)

    return text

# Use before storing
text = "User's phone is 555-123-4567"
safe_text = sanitize_memory(text)
# Stores: "User's phone is [REDACTED]"
```

---

## Troubleshooting

### API Key Issues

**Problem**: "Invalid API key"
**Solution**:
```bash
# Verify key
echo $MEM0_API_KEY

# Check key in Mem0 dashboard
# Re-generate if needed
```

### Memory Not Found

**Problem**: Can't retrieve stored memories
**Solution**:
```python
# Check if memory was actually stored
result = composio.tools.execute(
    action="MEM0_GET_MEMORIES",
    params={"user_id": "telegram_123456", "limit": 100},
    entity_id="default_user"
)

print(f"Total memories: {len(result.get('memories', []))}")

# Verify user_id matches
# Check if memory was deleted
```

### Search Not Working

**Problem**: Search returns no results
**Solution**:
- Use broader search terms
- Check spelling in query
- Try getting all memories first
- Verify memories exist for that user

---

## MCP Server Alternative

Community Mem0 MCP servers:

```bash
# Option 1: coleam00/mcp-mem0
npm install mcp-mem0

# Option 2: pinkpixel-dev/mem0-mcp
git clone https://github.com/pinkpixel-dev/mem0-mcp
cd mem0-mcp
npm install
```

Configure in MCP client:
```json
{
  "mem0": {
    "command": "node",
    "args": ["/path/to/mcp-mem0/dist/index.js"],
    "env": {
      "MEM0_API_KEY": "your_key_here"
    }
  }
}
```

---

## Resources

- Mem0 Docs: https://docs.mem0.ai
- Platform: https://mem0.ai
- GitHub: https://github.com/mem0ai/mem0
- Discord: Check mem0.ai website

---

## Next Steps

1. Get Mem0 API key
2. Test basic memory operations
3. Implement user preferences storage
4. Add email history tracking
5. Build context-aware email generation
6. Integrate with full agency workflow
