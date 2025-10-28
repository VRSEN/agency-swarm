# Composio SDK Setup Guide

## What is Composio?

Composio is a unified platform that provides AI agents with 100+ pre-built integrations through a single API. Instead of building and maintaining separate API connections for Gmail, Telegram, Slack, etc., you use Composio's standardized interface.

**Key Benefits**:
- One API key for multiple services
- Automatic OAuth flow handling
- Pre-configured actions for common operations
- Built-in error handling and retry logic
- Perfect for Agency Swarm and other agent frameworks
- Function calling ready for LLMs

---

## Installation

### Python (Recommended for Agency Swarm)

```bash
# Core Composio package
pip install composio-core

# For OpenAI/Agency Swarm integration
pip install composio-openai

# For other frameworks
pip install composio-langchain  # LangChain
pip install composio-crewai     # CrewAI
pip install composio-autogen    # AutoGen
```

### TypeScript/JavaScript

```bash
npm install @composio/core

# For OpenAI Agents SDK
npm install @composio/openai-agents

# For other frameworks
npm install @composio/langchain
npm install @composio/llamaindex
```

### Verify Installation

```bash
composio --version
```

---

## Getting Your Composio API Key

### Method 1: CLI Login (Recommended)

```bash
# This opens browser for authentication
composio login
```

The CLI will:
1. Open your default browser
2. Redirect to Composio authentication page
3. Create API key automatically
4. Store it in your system

### Method 2: Manual Setup

1. Visit https://app.composio.dev
2. Sign up for free account
3. Navigate to **Settings** > **API Keys**
4. Click **"Generate new API key"**
5. Copy the key (starts with `comp_`)
6. Save it securely

### Method 3: Environment Variable

```bash
# Set in terminal
export COMPOSIO_API_KEY=comp_your_api_key_here

# Or add to .env file
echo "COMPOSIO_API_KEY=comp_your_api_key_here" >> .env
```

### Verify Authentication

```bash
# Check if authenticated
composio whoami

# Should output your account email
```

---

## Basic Usage

### Python Example

```python
import os
from composio import Composio

# Initialize (uses COMPOSIO_API_KEY env var)
composio = Composio()

# Or provide key explicitly
composio = Composio(api_key="comp_your_api_key")

# Define user (unique identifier for connections)
user_id = "user@example.com"

# Get available toolkits
available_toolkits = composio.toolkits.list()
print("Available toolkits:", [tk.name for tk in available_toolkits])

# Get tools for specific toolkit
gmail_tools = composio.tools.get(
    toolkits=["GMAIL"],
    user_id=user_id
)

print(f"Gmail tools: {len(gmail_tools)} actions available")
```

### TypeScript Example

```typescript
import { Composio } from '@composio/core';

// Initialize
const composio = new Composio({
  apiKey: process.env.COMPOSIO_API_KEY,
});

// Get tools
const tools = await composio.tools.get({
  toolkits: ['GMAIL', 'TELEGRAM'],
  userId: 'user@example.com',
});

console.log(`Retrieved ${tools.length} tools`);
```

---

## Connecting Services (Authentication)

Composio handles authentication for each service you want to use. This is called creating a "connection" or "integration".

### Understanding Entities

In Composio, an **Entity** represents a user or system that needs access to external services.

```python
from composio import Composio

composio = Composio()

# Entity ID should be unique per user
# For single-user apps, can be constant
# For multi-user apps, use user email or ID
entity_id = "user@example.com"
```

### OAuth Services (Gmail, Slack, Notion, etc.)

For OAuth services, Composio provides a redirect URL that guides users through authentication:

```python
from composio import Composio

composio = Composio()
entity_id = "user@example.com"

# Initiate OAuth connection
connection = composio.connections.initiate(
    integration="GMAIL",
    entity_id=entity_id,
    redirect_url="http://localhost:8000/callback"  # Optional
)

# Get the authorization URL
print(f"Authorize at: {connection.auth_url}")

# User visits auth_url, grants permission
# Composio handles the callback and stores tokens
```

### API Key Services (Telegram Bot, ElevenLabs, etc.)

For API key-based services, provide credentials directly:

```python
from composio import Composio

composio = Composio()
entity_id = "user@example.com"

# Connect Telegram bot
composio.connections.initiate(
    integration="TELEGRAM",
    entity_id=entity_id,
    auth_config={
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN")
    }
)

# Connect ElevenLabs
composio.connections.initiate(
    integration="ELEVENLABS",
    entity_id=entity_id,
    auth_config={
        "api_key": os.getenv("ELEVENLABS_API_KEY")
    }
)
```

### Check Connection Status

```python
# List all connections for an entity
connections = composio.connections.list(entity_id=entity_id)

for conn in connections:
    print(f"{conn.integration}: {conn.status}")
    if conn.status == "active":
        print(f"  Connected successfully")
    else:
        print(f"  Error: {conn.error_message}")
```

---

## Using Composio Tools with Agency Swarm

### Step 1: Get Tools from Composio

```python
from composio import Composio
import os

composio = Composio()
entity_id = "user@example.com"

# Get all tools for specific toolkits
tools = composio.tools.get(
    toolkits=["GMAIL", "TELEGRAM", "ELEVENLABS"],
    entity_id=entity_id
)

print(f"Retrieved {len(tools)} tools")
```

### Step 2: Create Agency Swarm Agent

```python
from agency_swarm import Agent

email_agent = Agent(
    name="EmailAgent",
    description="Manages email drafts and sends emails via Gmail",
    instructions="""
    You are an email management assistant.
    You can create drafts, read emails, and send messages.
    Always confirm with the user before sending emails.
    """,
    tools=tools,  # Composio tools work directly!
)
```

### Step 3: Use in Agency

```python
from agency_swarm import Agency

# Create agency with Composio-powered agents
agency = Agency(
    agents=[email_agent, telegram_agent],
    shared_instructions="You are part of a voice-first email system"
)

# Run agency
agency.demo_gradio()
```

---

## Tool Execution

### Manual Tool Execution

```python
from composio import Composio

composio = Composio()
entity_id = "user@example.com"

# Execute a specific tool/action
result = composio.tools.execute(
    action="GMAIL_SEND_EMAIL",
    params={
        "to": "recipient@example.com",
        "subject": "Test Email",
        "body": "This is a test email from Composio"
    },
    entity_id=entity_id
)

print(f"Result: {result}")
```

### With OpenAI Function Calling

```python
from openai import OpenAI
from composio import Composio

openai_client = OpenAI()
composio = Composio()
entity_id = "user@example.com"

# Get tools in OpenAI format
tools = composio.tools.get(
    toolkits=["GMAIL"],
    entity_id=entity_id
)

# Use with OpenAI chat completion
response = openai_client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "Send an email to test@example.com"}
    ],
    tools=tools
)

# Composio handles execution automatically
```

---

## Advanced Configuration

### Custom Auth Configs

For services requiring special authentication:

```python
from composio import Composio

composio = Composio()

# Create custom auth configuration
auth_config = composio.auth_configs.create(
    integration="CUSTOM_SERVICE",
    auth_mode="API_KEY",
    config={
        "api_key": "your_custom_key",
        "base_url": "https://api.custom-service.com"
    }
)
```

### Webhook Integration

Composio supports webhooks for real-time updates:

```python
# Set up webhook for incoming Telegram messages
webhook = composio.webhooks.create(
    integration="TELEGRAM",
    entity_id=entity_id,
    callback_url="https://your-server.com/webhook",
    events=["message.new"]
)

print(f"Webhook URL: {webhook.url}")
```

### Custom Tool Parameters

```python
# Get tools with custom filters
tools = composio.tools.get(
    toolkits=["GMAIL"],
    entity_id=entity_id,
    tags=["send", "draft"]  # Only get send and draft-related tools
)

# Get specific actions
specific_tools = composio.tools.get(
    actions=["GMAIL_SEND_EMAIL", "GMAIL_CREATE_DRAFT"],
    entity_id=entity_id
)
```

---

## Best Practices

### 1. Use Environment Variables

```python
import os
from dotenv import load_dotenv

load_dotenv()  # Load from .env file

composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
```

### 2. Handle Errors Gracefully

```python
from composio import ComposioError

try:
    result = composio.tools.execute(
        action="GMAIL_SEND_EMAIL",
        params={...},
        entity_id=entity_id
    )
except ComposioError as e:
    print(f"Error executing tool: {e.message}")
    print(f"Error code: {e.code}")
```

### 3. Use Unique Entity IDs

```python
# Bad - same entity for all users
entity_id = "default_user"

# Good - unique per user
entity_id = f"user_{user_database_id}"
# or
entity_id = user_email_address
```

### 4. Cache Tool Definitions

```python
# Fetch tools once and reuse
if not hasattr(self, '_tools_cache'):
    self._tools_cache = composio.tools.get(
        toolkits=["GMAIL", "TELEGRAM"],
        entity_id=entity_id
    )

tools = self._tools_cache
```

### 5. Monitor Connections

```python
# Regularly check connection health
def check_connections(entity_id):
    connections = composio.connections.list(entity_id=entity_id)

    for conn in connections:
        if conn.status != "active":
            print(f"Warning: {conn.integration} is {conn.status}")
            # Reinitiate connection
            composio.connections.initiate(
                integration=conn.integration,
                entity_id=entity_id
            )
```

---

## Troubleshooting

### "Authentication failed" Error

```bash
# Clear stored credentials
composio logout

# Re-authenticate
composio login

# Verify
composio whoami
```

### Connection Not Active

```python
# Check connection status
connections = composio.connections.list(entity_id="user@example.com")

# Reconnect if needed
for conn in connections:
    if conn.status != "active":
        # Delete old connection
        composio.connections.delete(
            integration=conn.integration,
            entity_id="user@example.com"
        )

        # Create new connection
        composio.connections.initiate(
            integration=conn.integration,
            entity_id="user@example.com"
        )
```

### Rate Limiting

Composio has rate limits on API calls:

```python
from time import sleep

# Add delays between requests
for action in actions:
    result = composio.tools.execute(...)
    sleep(0.5)  # 500ms delay
```

### OAuth Token Expired

Composio automatically refreshes OAuth tokens, but if issues occur:

```python
# Force token refresh
composio.connections.refresh(
    integration="GMAIL",
    entity_id="user@example.com"
)
```

---

## CLI Commands Reference

```bash
# Authentication
composio login                    # Login via browser
composio logout                   # Logout
composio whoami                   # Show current user

# Toolkits
composio toolkits list            # List all available toolkits
composio tools list --toolkit GMAIL  # List tools in toolkit

# Connections
composio connections list         # Show all connections
composio connections add GMAIL    # Add new connection

# Updates
composio update                   # Update Composio CLI
```

---

## Example: Complete Setup Script

```python
#!/usr/bin/env python3
"""
Complete Composio setup for voice-email-telegram project
"""

import os
from dotenv import load_dotenv
from composio import Composio

# Load environment variables
load_dotenv()

# Initialize Composio
composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))

# Define entity
entity_id = "voice-email-bot@system"

print("Setting up Composio connections...")

# 1. Connect Telegram (API key auth)
print("\n1. Connecting Telegram...")
try:
    telegram_conn = composio.connections.initiate(
        integration="TELEGRAM",
        entity_id=entity_id,
        auth_config={
            "bot_token": os.getenv("TELEGRAM_BOT_TOKEN")
        }
    )
    print("   ✓ Telegram connected")
except Exception as e:
    print(f"   ✗ Telegram failed: {e}")

# 2. Connect Gmail (OAuth)
print("\n2. Connecting Gmail...")
print("   Opening browser for Gmail authentication...")
try:
    gmail_conn = composio.connections.initiate(
        integration="GMAIL",
        entity_id=entity_id
    )
    print(f"   Visit: {gmail_conn.auth_url}")
    print("   Waiting for authorization...")
    # Note: In production, you'd implement proper callback handling
    print("   ✓ Gmail connection initiated")
except Exception as e:
    print(f"   ✗ Gmail failed: {e}")

# 3. Connect ElevenLabs
print("\n3. Connecting ElevenLabs...")
try:
    elevenlabs_conn = composio.connections.initiate(
        integration="ELEVENLABS",
        entity_id=entity_id,
        auth_config={
            "api_key": os.getenv("ELEVENLABS_API_KEY")
        }
    )
    print("   ✓ ElevenLabs connected")
except Exception as e:
    print(f"   ✗ ElevenLabs failed: {e}")

# 4. Connect Mem0
print("\n4. Connecting Mem0...")
try:
    mem0_conn = composio.connections.initiate(
        integration="MEM0",
        entity_id=entity_id,
        auth_config={
            "api_key": os.getenv("MEM0_API_KEY")
        }
    )
    print("   ✓ Mem0 connected")
except Exception as e:
    print(f"   ✗ Mem0 failed: {e}")

# Verify all connections
print("\n" + "="*50)
print("Connection Status:")
print("="*50)

connections = composio.connections.list(entity_id=entity_id)
for conn in connections:
    status_icon = "✓" if conn.status == "active" else "✗"
    print(f"{status_icon} {conn.integration}: {conn.status}")

print("\n" + "="*50)
print("Setup complete! All connections configured.")
print("="*50)
```

---

## Next Steps

1. **Complete authentication** for all services
2. **Test individual tools** to verify connections
3. **Create Agency Swarm agents** using Composio tools
4. **Implement error handling** for production
5. **Set up monitoring** for connection health

For detailed integration with each service, see:
- `TELEGRAM_INTEGRATION.md`
- `GMAIL_INTEGRATION.md`
- `ELEVENLABS_INTEGRATION.md`
- `MEM0_INTEGRATION.md`

---

## Resources

- Official Docs: https://docs.composio.dev
- GitHub: https://github.com/ComposioHQ/composio
- Discord: https://composio.dev/discord
- Examples: https://github.com/ComposioHQ/composio/tree/master/examples
- API Reference: https://docs.composio.dev/api-reference
