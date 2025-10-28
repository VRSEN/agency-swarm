# API Integration Guide: Voice-First Email Draft Approval System

## Project Overview
Voice-first email draft approval system that uses Telegram as the interface, with voice interactions powered by ElevenLabs, email management through Gmail, and persistent memory via Mem0.

## Integration Architecture

### Primary Integration Method: Composio SDK
**Why Composio?**
- Unified API for multiple services (Gmail, Telegram, ElevenLabs, Mem0)
- Built-in authentication handling (OAuth2, API keys)
- Pre-configured actions for common operations
- Excellent support for Agency Swarm and OpenAI agents
- Automatic tool registration and function calling
- 100+ integrations available

### Alternative: MCP Servers (Model Context Protocol)
MCP servers are also available for individual services, offering standardized tool interfaces with zero maintenance. However, for this project, **Composio is recommended** as it provides:
- Unified authentication across all services
- Consistent API across different tools
- Better integration with Agency Swarm
- Simplified multi-service coordination

---

## Required Integrations

### 1. Composio SDK (Core Platform)

**Package**: `composio-openai` (Python) or `@composio/openai-agents` (TypeScript)

**Installation**:
```bash
# Python
pip install composio-openai

# TypeScript
npm install @composio/openai-agents @openai/agents
```

**Authentication**: Composio API Key

**Setup**:
```python
from composio import Composio

# Initialize with API key
composio = Composio(api_key="your-composio-api-key")

# Or use CLI login
# Run: composio login
```

**Getting Composio API Key**:
1. Visit https://app.composio.dev
2. Sign up for a free account
3. Navigate to Settings > API Keys
4. Click "Generate new API key"
5. Copy and save the key immediately
6. Set as environment variable: `export COMPOSIO_API_KEY=your_key`

**Free Tier**: Yes, available with generous limits

---

### 2. Telegram Integration

**Via Composio**: `TELEGRAM` toolkit

**Authentication Methods**:
- Bot Token (recommended for bots)
- API ID + API Hash (for user accounts)

**Getting Telegram Bot Token**:
1. Open Telegram and search for `@BotFather`
2. Start a chat and send `/newbot`
3. Follow prompts to name your bot
4. Copy the bot token provided (format: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)
5. Save securely for Composio connection

**Getting Telegram API ID & Hash** (if needed):
1. Visit https://my.telegram.org
2. Log in with your phone number
3. Navigate to "API development tools"
4. Create a new application
5. Copy `api_id` and `api_hash`
6. Note: Keep these credentials secure

**Composio Setup**:
```python
from composio import Composio

composio = Composio(api_key="your-composio-api-key")

# Get Telegram tools
telegram_tools = composio.tools.get(
    toolkits=["TELEGRAM"],
    user_id="user@example.com"
)
```

**Available Actions**:
- Send text messages to chats
- Send files/documents to chats
- Read incoming messages
- Manage bot commands
- Handle user interactions

**MCP Alternative**: Multiple MCP servers available
- `chigwell/telegram-mcp` - Full-featured Telethon integration
- `Muhammad18557/telegram-mcp` - Message search and sending
- Installation: `npm install telegram-mcp` or via GitHub

---

### 3. Gmail Integration

**Via Composio**: `GMAIL` toolkit

**Authentication**: OAuth2 (handled by Composio)

**Getting Gmail API Credentials**:
1. Visit https://console.cloud.google.com
2. Create a new project or select existing
3. Enable Gmail API:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Gmail API"
   - Click "Enable"
4. Configure OAuth Consent Screen:
   - Go to "APIs & Services" > "OAuth consent screen"
   - Select "External" (unless you have Google Workspace)
   - Fill in required fields (app name, user support email)
   - Add test users if in testing mode
5. Create OAuth Client ID:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Select "Desktop app" or "Web application"
   - Download credentials JSON file
6. Connect via Composio:
   - Composio handles the OAuth flow automatically
   - You'll authenticate through browser

**Composio Setup**:
```python
from composio import Composio

composio = Composio(api_key="your-composio-api-key")

# Get Gmail tools
gmail_tools = composio.tools.get(
    toolkits=["GMAIL"],
    user_id="user@example.com"
)

# Composio will prompt for Gmail OAuth authentication
```

**Available Actions**:
- `GMAIL_SEND_EMAIL` - Send new emails
- `GMAIL_REPLY_TO_THREAD` - Reply to existing threads
- `GMAIL_FETCH_EMAILS` - Retrieve emails with filters
- `GMAIL_CREATE_DRAFT` - Create email drafts
- `GMAIL_LIST_DRAFTS` - List all drafts
- `GMAIL_READ_DRAFT` - Read draft content
- `GMAIL_UPDATE_DRAFT` - Modify drafts
- `GMAIL_DELETE_DRAFT` - Remove drafts
- Label management (create, list, apply)
- Search with advanced filters

**MCP Alternative**: Multiple MCP servers available
- `GongRzhe/Gmail-MCP-Server` - Full Gmail integration with auto-auth
- `jeremyjordan/mcp-gmail` - Python-based Gmail MCP
- Installation: `npm install gmail-mcp-server` or via GitHub

---

### 4. ElevenLabs Voice Integration

**Via Composio**: `ELEVENLABS` integration

**Authentication**: ElevenLabs API Key

**Getting ElevenLabs API Key**:
1. Visit https://elevenlabs.io
2. Sign up for free account (no credit card required)
3. Navigate to Profile Settings
4. Find "API Keys" section
5. Click "Generate API Key"
6. Copy the `xi-api-key` value
7. Save securely

**Free Tier Details**:
- 10,000-20,000 characters per month
- 100 requests per minute
- Non-commercial use only
- Good for testing and prototyping

**Composio Setup**:
```python
from composio import Composio

composio = Composio(api_key="your-composio-api-key")

# Get ElevenLabs tools
elevenlabs_tools = composio.tools.get(
    toolkits=["ELEVENLABS"],
    user_id="user@example.com"
)
```

**Available Actions**:
- Text-to-speech conversion
- Voice cloning
- Audio transcription
- Create audio projects
- Dub videos/audio files
- Manage voice models
- Create AudioNative embeddable players
- Pronunciation dictionary management

**MCP Alternative**: Official ElevenLabs MCP Server
- Package: `@elevenlabs/elevenlabs-mcp` (official)
- Installation: `npm install @elevenlabs/elevenlabs-mcp`
- GitHub: https://github.com/elevenlabs/elevenlabs-mcp
- Features: TTS, transcription, voice cloning, outbound calls

---

### 5. Mem0 Memory Integration

**Via Composio**: `MEM0` toolkit

**Authentication**: Mem0 API Key

**Getting Mem0 API Key**:
1. Visit https://mem0.ai
2. Sign up for account
3. Navigate to Dashboard
4. Go to "API Keys" section
5. Generate new API key
6. Copy and save the key
7. Set as environment variable: `export MEM0_API_KEY=your_key`

**Composio Setup**:
```python
from composio import Composio

composio = Composio(api_key="your-composio-api-key")

# Get Mem0 tools
mem0_tools = composio.tools.get(
    toolkits=["MEM0"],
    user_id="user@example.com"
)
```

**Available Actions**:
- Store memories/context
- Retrieve memories by user
- Search stored information
- Update existing memories
- Delete memories
- Organize knowledge base

**MCP Alternative**: Multiple MCP servers available
- `coleam00/mcp-mem0` - Long-term memory for agents
- `pinkpixel-dev/mem0-mcp` - Autonomous memory system
- Official: OpenMemory MCP (private, local-first)
- Installation: `npm install mcp-mem0` or via GitHub

---

## Complete Setup Process

### Step 1: Install Composio
```bash
# Install core Composio package
pip install composio-openai

# For Agency Swarm compatibility
pip install composio-openai openai
```

### Step 2: Authenticate Composio
```bash
# Option 1: CLI login (recommended)
composio login

# Option 2: Set API key manually
export COMPOSIO_API_KEY=your_composio_api_key
```

### Step 3: Collect All API Keys

Create a `.env` file:
```env
# Core OpenAI (required)
OPENAI_API_KEY=sk-...

# Composio Platform
COMPOSIO_API_KEY=your_composio_key

# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
# OR for user account access:
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890

# ElevenLabs
ELEVENLABS_API_KEY=xi_...

# Mem0
MEM0_API_KEY=your_mem0_key

# Gmail - OAuth handled by Composio
# No manual key needed, will authenticate via browser
```

### Step 4: Connect Services via Composio

```python
from composio import Composio

# Initialize Composio
composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))

# Define user (unique identifier for auth/connections)
user_id = "user@example.com"

# Get all toolkits
tools = composio.tools.get(
    user_id=user_id,
    toolkits=["TELEGRAM", "GMAIL", "ELEVENLABS", "MEM0"]
)

# Connect individual services (follows OAuth flow where needed)
composio.connections.initiate(
    integration="GMAIL",
    user_id=user_id
)

composio.connections.initiate(
    integration="TELEGRAM",
    user_id=user_id,
    auth_config={
        "bot_token": os.getenv("TELEGRAM_BOT_TOKEN")
    }
)
```

### Step 5: Verify Connections
```python
# List all active connections
connections = composio.connections.list(user_id=user_id)

for conn in connections:
    print(f"{conn.integration}: {conn.status}")
```

---

## Integration with Agency Swarm

### Creating Tools from Composio

```python
from agency_swarm import Agent
from composio import Composio

# Initialize Composio
composio = Composio()
user_id = "user@example.com"

# Get tools for specific agent
telegram_tools = composio.tools.get(
    toolkits=["TELEGRAM"],
    user_id=user_id
)

gmail_tools = composio.tools.get(
    toolkits=["GMAIL"],
    user_id=user_id
)

# Create agent with Composio tools
email_agent = Agent(
    name="Email Draft Agent",
    description="Manages email drafts via Gmail",
    tools=gmail_tools,  # Composio tools are directly compatible
)

telegram_agent = Agent(
    name="Telegram Interface Agent",
    description="Handles Telegram interactions",
    tools=telegram_tools,
)
```

---

## Cost Summary

| Service | Free Tier | Cost After Free Tier |
|---------|-----------|---------------------|
| **OpenAI API** | No | $0.01-0.03 per 1K tokens |
| **Composio** | Yes (generous) | Free for most use cases |
| **Telegram** | Yes (unlimited) | Free |
| **Gmail API** | Yes (generous) | Free for most use cases |
| **ElevenLabs** | 10-20K chars/month | $5/month (Starter) |
| **Mem0** | Check platform | Varies by usage |

**Recommended Budget**: $5-15/month for testing and light production use

---

## Troubleshooting

### Composio Authentication Issues
```bash
# Re-authenticate
composio logout
composio login

# Check current authentication
composio whoami
```

### Connection Problems
```python
# List all connections and their status
connections = composio.connections.list(user_id="user@example.com")
for conn in connections:
    print(f"{conn.integration}: {conn.status}")
    if conn.status != "active":
        print(f"  Error: {conn.error_message}")
```

### Gmail OAuth Not Working
1. Ensure Gmail API is enabled in Google Cloud Console
2. Check OAuth consent screen is configured
3. Verify redirect URIs are correct
4. For testing, add your email as test user
5. Check Composio dashboard for connection status

### Telegram Bot Not Responding
1. Verify bot token is correct
2. Check bot is not blocked
3. Ensure bot has necessary permissions
4. Test bot independently using `@BotFather`

---

## Next Steps

1. **Set up OpenAI API key** (required for all agents)
2. **Create Composio account** and get API key
3. **Create Telegram bot** via BotFather
4. **Set up Gmail OAuth** via Google Cloud Console
5. **Get ElevenLabs API key** (free tier)
6. **Get Mem0 API key**
7. **Install and configure** all services
8. **Test each integration** independently
9. **Build Agency Swarm agents** with Composio tools
10. **Deploy and monitor**

---

## Additional Resources

### Documentation Links
- Composio Docs: https://docs.composio.dev
- Composio GitHub: https://github.com/ComposioHQ/composio
- Agency Swarm: https://github.com/VRSEN/agency-swarm
- Telegram Bot API: https://core.telegram.org/bots/api
- Gmail API: https://developers.google.com/gmail/api
- ElevenLabs API: https://elevenlabs.io/docs
- Mem0 Docs: https://docs.mem0.ai

### Community Support
- Composio Discord: Available via their website
- Agency Swarm Discord: Check GitHub repo
- Stack Overflow: Tag with service names

---

## License & Terms

Ensure compliance with:
- OpenAI Usage Policies
- Telegram Bot API Terms
- Google API Terms of Service
- ElevenLabs Terms of Service
- Mem0 Terms of Service

Always review rate limits and usage quotas for production deployments.
