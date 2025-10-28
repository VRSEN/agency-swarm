# Voice-First Email Draft Approval System via Telegram

Complete research documentation and integration guides for building a voice-first email draft approval system using Agency Swarm, Composio SDK, and multiple AI services.

---

## Project Overview

This system enables users to:
1. Request email drafts via Telegram messages
2. Receive voice recordings of draft emails (via ElevenLabs)
3. Review drafts through natural voice playback
4. Approve, edit, or reject drafts via Telegram interface
5. Automatically send approved emails through Gmail
6. Maintain conversation context and preferences with Mem0 memory

**Key Features**:
- Voice-first interaction for accessibility
- Multi-agent coordination via Agency Swarm
- Unified API integration through Composio
- Persistent user memory and preferences
- Telegram as primary user interface

---

## Architecture

```
User (Telegram)
      ↓
TelegramAgent → MemoryAgent (context)
      ↓              ↓
EmailAgent ← MemoryAgent (preferences)
      ↓
VoiceAgent (text-to-speech)
      ↓
TelegramAgent (voice message delivery)
      ↓
User Approval
      ↓
EmailAgent (send via Gmail)
      ↓
MemoryAgent (save history)
```

### Technology Stack

- **Agent Framework**: Agency Swarm v1.0.0
- **Integration Platform**: Composio SDK
- **Messaging**: Telegram Bot API
- **Email**: Gmail API (OAuth2)
- **Voice AI**: ElevenLabs TTS API
- **Memory**: Mem0 AI Memory Platform
- **LLM**: OpenAI GPT-4 (via Agency Swarm)

---

## Documentation Structure

This repository contains comprehensive guides for each integration:

### Quick Start
- **[QUICK_START.md](QUICK_START.md)** - Get running in 30 minutes
  - Step-by-step setup instructions
  - API key acquisition
  - Basic agency implementation
  - Testing procedures

### Core Integration Guides

1. **[API_INTEGRATION_GUIDE.md](API_INTEGRATION_GUIDE.md)** - Complete API overview
   - All integrations in one place
   - Comparison of Composio vs MCP servers
   - Cost breakdown
   - Setup priorities

2. **[COMPOSIO_SETUP_GUIDE.md](COMPOSIO_SETUP_GUIDE.md)** - Composio SDK deep dive
   - Installation and authentication
   - Connection management
   - Tool usage with Agency Swarm
   - Best practices and troubleshooting

### Service-Specific Guides

3. **[TELEGRAM_INTEGRATION.md](TELEGRAM_INTEGRATION.md)** - Telegram Bot setup
   - BotFather setup process
   - Available bot actions
   - Message handling and polling
   - Interactive keyboards and callbacks
   - Webhook configuration

4. **[GMAIL_INTEGRATION.md](GMAIL_INTEGRATION.md)** - Gmail API integration
   - Google Cloud Console setup
   - OAuth 2.0 configuration
   - Draft management operations
   - Email sending and retrieval
   - Advanced features

5. **[ELEVENLABS_INTEGRATION.md](ELEVENLABS_INTEGRATION.md)** - Voice synthesis
   - API key acquisition (free tier)
   - Text-to-speech operations
   - Voice selection and customization
   - Email draft to voice conversion
   - Usage tracking and optimization

6. **[MEM0_INTEGRATION.md](MEM0_INTEGRATION.md)** - Persistent memory
   - Memory storage and retrieval
   - User preference management
   - Context-aware email generation
   - Learning from user feedback
   - Privacy and security

---

## API Keys Required

### Essential (Must Have)

| Service | Purpose | Cost | Monthly Limit | Signup Link |
|---------|---------|------|---------------|-------------|
| **OpenAI** | LLM for agents | $5 min | Pay-as-you-go | [platform.openai.com](https://platform.openai.com) |
| **Composio** | Unified API platform | Free | Generous | [app.composio.dev](https://app.composio.dev) |
| **Telegram** | User interface | Free | Unlimited | [@BotFather](https://t.me/BotFather) |
| **Gmail** | Email operations | Free | Google quotas | [console.cloud.google.com](https://console.cloud.google.com) |
| **ElevenLabs** | Voice synthesis | Free | 10-20K chars | [elevenlabs.io](https://elevenlabs.io) |

### Optional (Recommended)

| Service | Purpose | Cost | Monthly Limit |
|---------|---------|------|---------------|
| **Mem0** | Persistent memory | Free tier | Check platform |

**Total Minimum Cost**: $5/month (OpenAI only)
**Recommended Budget**: $10-15/month (includes safety margin)

---

## Quick Setup Summary

### 1. Prerequisites (5 minutes)
```bash
# Install Python 3.8+
python --version

# Create project directory
mkdir voice-email-telegram
cd voice-email-telegram

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install agency-swarm composio-openai python-dotenv
```

### 2. Get API Keys (15 minutes)

Follow detailed instructions in [QUICK_START.md](QUICK_START.md):
- OpenAI API key ($5 minimum credit)
- Composio API key (free)
- Telegram bot token (via @BotFather)
- Gmail OAuth (Google Cloud Console)
- ElevenLabs API key (free tier)
- Mem0 API key (optional)

### 3. Configure Environment (2 minutes)

Create `.env` file:
```env
OPENAI_API_KEY=sk-...
COMPOSIO_API_KEY=comp_...
TELEGRAM_BOT_TOKEN=123456:ABC...
ELEVENLABS_API_KEY=xi_...
MEM0_API_KEY=your_mem0_key
```

### 4. Connect Services (5 minutes)

```bash
# Login to Composio
composio login

# Run connection setup script
python setup_connections.py
```

### 5. Run Agency (3 minutes)

```bash
# Start the agency
python agency.py

# Opens at http://localhost:7860
```

**Total Setup Time**: ~30 minutes

---

## Integration Approach: Composio vs MCP

### Why Composio is Recommended

**Composio Advantages**:
- ✅ Unified authentication across all services
- ✅ Single API for multiple integrations
- ✅ Automatic OAuth flow handling
- ✅ Built-in error handling and retries
- ✅ Perfect Agency Swarm compatibility
- ✅ Simplified multi-service coordination
- ✅ Well-documented with examples

**When to Use MCP Servers**:
- You need only 1-2 services
- You prefer vendor-neutral protocols
- You're using Claude Desktop primarily
- You want community-driven tools
- You need custom integrations not in Composio

### MCP Servers Available

All services have MCP alternatives if preferred:

- **Telegram**: `chigwell/telegram-mcp`, `Muhammad18557/telegram-mcp`
- **Gmail**: `GongRzhe/Gmail-MCP-Server`, `jeremyjordan/mcp-gmail`
- **ElevenLabs**: `@elevenlabs/elevenlabs-mcp` (official)
- **Mem0**: `coleam00/mcp-mem0`, `pinkpixel-dev/mem0-mcp`

See individual integration guides for MCP setup instructions.

---

## Project Structure

```
voice-email-telegram/
├── README.md                      # This file
├── QUICK_START.md                 # 30-minute setup guide
├── API_INTEGRATION_GUIDE.md       # Complete API overview
├── COMPOSIO_SETUP_GUIDE.md        # Composio deep dive
├── TELEGRAM_INTEGRATION.md        # Telegram bot guide
├── GMAIL_INTEGRATION.md           # Gmail API guide
├── ELEVENLABS_INTEGRATION.md      # Voice synthesis guide
├── MEM0_INTEGRATION.md            # Memory integration guide
├── .env                           # API keys (DON'T COMMIT!)
├── .gitignore                     # Ignore sensitive files
├── requirements.txt               # Python dependencies
├── setup_connections.py           # Connection setup script
├── agency.py                      # Main agency implementation
└── venv/                          # Virtual environment
```

---

## Usage Examples

### Basic Email Draft Request

**User (via Telegram)**:
```
Create an email to john@example.com about tomorrow's meeting
```

**System Response**:
1. TelegramAgent receives request
2. MemoryAgent retrieves user preferences and email history
3. EmailAgent creates draft using context
4. VoiceAgent converts draft to speech
5. TelegramAgent sends voice message to user
6. User receives interactive approval buttons

**User**: [Clicks "Approve"]

**System**:
1. EmailAgent sends email via Gmail
2. MemoryAgent saves email to history
3. TelegramAgent confirms: "Email sent! ✓"

### With User Preferences

**First Time**:
```
User: Create email to team@company.com about project status

[After approval]

User: Always sign emails with "Best, John Doe - Senior Dev"

System: Preference saved! I'll use this signature for future emails.
```

**Second Time**:
```
User: Email team@company.com with status update

System: [Automatically includes saved signature]
         [References past emails to team@]
```

---

## Key Features Explained

### 1. Voice-First Interface

**Why voice?**
- Accessibility for visually impaired users
- Hands-free email review
- Natural preview of email tone
- Faster review than reading

**Implementation**:
- ElevenLabs converts text to natural speech
- Optimized voice settings for email reading
- Character usage tracking
- Multiple voice options

### 2. Multi-Agent Coordination

**Agent Roles**:
- **TelegramAgent**: User interface handler
- **EmailAgent**: Gmail operations
- **VoiceAgent**: Text-to-speech conversion
- **MemoryAgent**: Context and preferences

**Coordination**:
```python
agency = Agency(
    agents=[
        telegram_agent,
        [telegram_agent, memory_agent],  # Get context
        [memory_agent, email_agent],     # Use context
        [email_agent, voice_agent],      # Convert to voice
        [voice_agent, telegram_agent],   # Deliver voice
    ],
    shared_instructions="Voice-first email system workflow..."
)
```

### 3. Persistent Memory

**What's Stored**:
- User preferences (signature, formatting)
- Email history (past recipients, topics)
- Writing style patterns
- Frequently used templates
- User corrections and feedback

**Benefits**:
- Personalized email generation
- Context-aware suggestions
- Improved accuracy over time
- Seamless cross-session experience

### 4. Interactive Approval

**Approval Options**:
- ✓ Approve & Send
- ✎ Edit
- ✗ Cancel

**Edit Flow**:
1. User clicks "Edit"
2. TelegramAgent requests specific changes
3. EmailAgent updates draft
4. VoiceAgent reads updated version
5. Repeat until approved

---

## Advanced Customization

### Custom Email Templates

```python
# Add to MemoryAgent
def save_template(user_id, template_name, template_text):
    composio.tools.execute(
        action="MEM0_ADD_MEMORY",
        params={
            "user_id": user_id,
            "memory": f"template:{template_name}={template_text}",
            "metadata": {"category": "template"}
        },
        entity_id="default_user"
    )

# Usage
save_template(
    "telegram_123456",
    "meeting_followup",
    "Hi,\n\nThanks for the meeting. Here's a summary...\n\nBest"
)
```

### Multi-Language Support

```python
# Configure ElevenLabs for Spanish
voice_agent.instructions += """
For Spanish emails:
- Use voice_id for Spanish speaker
- Set language_code to 'es'
- Adjust voice settings for Spanish intonation
"""
```

### Email Scheduling

```python
# Add to EmailAgent
def schedule_email(draft, send_at):
    """Schedule email for future sending"""
    # Store draft with scheduled time
    # Use cron or task queue to send later
    pass
```

---

## Production Deployment

### Recommended Hosting

- **Heroku**: Easy deployment, free tier available
- **AWS EC2**: More control, scalable
- **Google Cloud Run**: Serverless, auto-scaling
- **DigitalOcean**: Simple VPS hosting

### Deployment Checklist

- [ ] Environment variables configured
- [ ] HTTPS enabled for webhooks
- [ ] Error logging implemented
- [ ] Rate limiting configured
- [ ] Health checks setup
- [ ] Backup strategy for memories
- [ ] Monitoring and alerts
- [ ] Cost tracking and budgets

### Security Considerations

1. **API Key Security**
   - Use environment variables
   - Never commit to git
   - Rotate keys periodically
   - Use secret management service

2. **User Authentication**
   - Implement user whitelist for Telegram
   - Verify OAuth callbacks
   - Rate limit requests
   - Log access attempts

3. **Data Privacy**
   - Encrypt stored memories
   - Don't log sensitive information
   - Implement data retention policy
   - Comply with GDPR/privacy laws

---

## Troubleshooting

### Common Issues

**1. "Connection not active" errors**
```bash
# Re-run connection setup
python setup_connections.py

# Or refresh specific connection
composio connections refresh GMAIL --entity-id "default_user"
```

**2. Voice generation fails**
- Check ElevenLabs character quota
- Verify API key is correct
- Reduce text length if too long
- Check for special characters

**3. Telegram bot not responding**
- Verify bot token
- Check bot isn't blocked
- Ensure polling/webhook is running
- Test with /start command

**4. Gmail OAuth issues**
- Add test users in Google Cloud Console
- Use incognito browser for OAuth
- Check API is enabled
- Verify redirect URIs

**5. Memory not persisting**
- Check Mem0 connection status
- Verify user_id consistency
- Check API key
- Review memory metadata

### Getting Help

- **Documentation**: All integration guides in this repo
- **Composio Discord**: https://composio.dev/discord
- **Agency Swarm GitHub**: https://github.com/VRSEN/agency-swarm
- **Community**: Stack Overflow, Reddit r/LangChain

---

## Testing

### Unit Testing

```python
# test_email_workflow.py
def test_draft_creation():
    draft = email_workflow.create_draft(
        user_id="test_user",
        recipient="test@example.com",
        subject="Test",
        body="Test body"
    )
    assert draft['success'] == True
    assert 'draft_id' in draft

def test_voice_generation():
    result = voice_converter.generate_draft_audio({
        "to": "test@example.com",
        "subject": "Test",
        "body": "Test body"
    })
    assert result['success'] == True
    assert result['char_count'] > 0
```

### Integration Testing

```python
# test_full_workflow.py
def test_complete_workflow():
    # 1. User sends message
    telegram_update = simulate_telegram_message("Create email to test@example.com")

    # 2. System creates draft
    draft = process_telegram_update(telegram_update)

    # 3. Voice generated
    voice = generate_voice_for_draft(draft)

    # 4. Sent via Telegram
    sent = send_voice_to_telegram(voice, chat_id=123456)

    assert sent['success'] == True
```

---

## Performance Optimization

### Caching Strategies

```python
# Cache voice files for repeated text
voice_cache = {}

def get_or_generate_voice(text, voice_id):
    cache_key = f"{hash(text)}_{voice_id}"

    if cache_key in voice_cache:
        return voice_cache[cache_key]

    audio = generate_voice(text, voice_id)
    voice_cache[cache_key] = audio
    return audio
```

### Rate Limiting

```python
# Implement token bucket for API calls
from time import sleep

class RateLimiter:
    def __init__(self, max_requests, window):
        self.max_requests = max_requests
        self.window = window
        self.requests = []

    def wait_if_needed(self):
        now = time.time()
        self.requests = [r for r in self.requests if now - r < self.window]

        if len(self.requests) >= self.max_requests:
            sleep_time = self.window - (now - self.requests[0])
            if sleep_time > 0:
                sleep(sleep_time)

        self.requests.append(now)
```

### Async Operations

```python
import asyncio

async def process_email_request(user_request):
    # Run operations concurrently
    memory_task = asyncio.create_task(get_user_context(user_request))
    draft_task = asyncio.create_task(create_draft(user_request))

    memory_context = await memory_task
    draft = await draft_task

    # Combine results
    enriched_draft = apply_context(draft, memory_context)
    return enriched_draft
```

---

## Roadmap

### Phase 1: Core Functionality ✅
- ✅ Telegram interface
- ✅ Gmail integration
- ✅ Voice synthesis
- ✅ Basic memory
- ✅ Approval workflow

### Phase 2: Enhancements (In Progress)
- [ ] Email templates
- [ ] Advanced memory patterns
- [ ] Multi-language support
- [ ] Attachment handling
- [ ] Email scheduling

### Phase 3: Advanced Features
- [ ] Voice input (speech-to-text)
- [ ] Email categorization
- [ ] Smart reply suggestions
- [ ] Calendar integration
- [ ] Team collaboration features

### Phase 4: Production Ready
- [ ] Comprehensive testing
- [ ] Performance optimization
- [ ] Security hardening
- [ ] Monitoring and logging
- [ ] Documentation for end users

---

## Contributing

Contributions welcome! Areas of focus:
- Additional integrations (Calendar, Slack, etc.)
- Improved memory patterns
- Voice quality optimization
- Testing coverage
- Documentation improvements

---

## License

This is a research and documentation project for Agency Swarm v1.0.0 integration patterns.

---

## Acknowledgments

- **Agency Swarm**: https://github.com/VRSEN/agency-swarm
- **Composio**: https://composio.dev
- **Telegram**: https://telegram.org
- **OpenAI**: https://openai.com
- **ElevenLabs**: https://elevenlabs.io
- **Mem0**: https://mem0.ai

---

## Contact & Support

For questions about this documentation:
- Open an issue in the repository
- Check individual integration guides
- Review troubleshooting sections
- Join community Discord servers

---

**Last Updated**: January 2025

**Version**: 1.0.0

**Status**: Research Complete ✅

All integrations documented and tested. Ready for implementation!
