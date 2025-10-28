# Quick Start Guide: Voice-First Email Approval System

Get your voice-first email draft approval system running in 30 minutes.

---

## Prerequisites

- Python 3.8+ installed
- Node.js 14+ (optional, for TypeScript)
- Git installed
- Active internet connection
- Email account (Gmail recommended)
- Telegram account

---

## Step 1: Get All API Keys (15 minutes)

### 1.1 OpenAI API Key (Required)

**Time**: 5 minutes | **Cost**: $5 minimum

1. Go to https://platform.openai.com/api-keys
2. Sign up or log in
3. Click "Create new secret key"
4. Name it "voice-email-system"
5. Copy the key (starts with `sk-`)
6. Add billing at https://platform.openai.com/account/billing
7. Add minimum $5 credit

```bash
# Save to .env
echo "OPENAI_API_KEY=sk-your-key-here" >> .env
```

### 1.2 Composio API Key (Required)

**Time**: 2 minutes | **Cost**: Free

1. Go to https://app.composio.dev
2. Sign up with email
3. Navigate to Settings > API Keys
4. Click "Generate new API key"
5. Copy key (starts with `comp_`)

```bash
echo "COMPOSIO_API_KEY=comp_your-key-here" >> .env
```

### 1.3 Telegram Bot Token (Required)

**Time**: 3 minutes | **Cost**: Free

1. Open Telegram
2. Search for `@BotFather`
3. Send `/newbot`
4. Follow prompts:
   - Bot name: "Voice Email Assistant"
   - Username: "your_unique_bot" (must end in 'bot')
5. Copy the token (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

```bash
echo "TELEGRAM_BOT_TOKEN=your-token-here" >> .env
```

### 1.4 ElevenLabs API Key (Required for Voice)

**Time**: 3 minutes | **Cost**: Free (10K chars/month)

1. Go to https://elevenlabs.io
2. Sign up (no credit card required)
3. Click profile icon > Settings
4. Find "API Keys" section
5. Click "Generate API Key"
6. Copy key (starts with `xi_`)

```bash
echo "ELEVENLABS_API_KEY=xi_your-key-here" >> .env
```

### 1.5 Mem0 API Key (Optional - for memory)

**Time**: 2 minutes | **Cost**: Free tier available

1. Go to https://mem0.ai
2. Sign up for account
3. Navigate to Dashboard
4. Go to API Keys
5. Generate new key

```bash
echo "MEM0_API_KEY=your-mem0-key" >> .env
```

---

## Step 2: Install Dependencies (5 minutes)

### 2.1 Clone or Create Project

```bash
# Create project directory
mkdir voice-email-telegram
cd voice-email-telegram

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate
```

### 2.2 Install Packages

```bash
# Install core dependencies
pip install agency-swarm composio-openai python-dotenv

# Optional: Install CLI tools
pip install composio-core
```

### 2.3 Verify Installation

```bash
python -c "import agency_swarm; import composio; print('✓ All imports successful')"
```

---

## Step 3: Configure Composio Connections (5 minutes)

### 3.1 Login to Composio

```bash
composio login
```

This opens your browser for authentication.

### 3.2 Connect Services

Create `setup_connections.py`:

```python
#!/usr/bin/env python3
import os
from dotenv import load_dotenv
from composio import Composio

load_dotenv()

composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
entity_id = "default_user"

print("Setting up connections...")

# Connect Telegram
print("\n1. Connecting Telegram...")
try:
    composio.connections.initiate(
        integration="TELEGRAM",
        entity_id=entity_id,
        auth_config={"bot_token": os.getenv("TELEGRAM_BOT_TOKEN")}
    )
    print("   ✓ Telegram connected")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Connect Gmail (requires browser authentication)
print("\n2. Connecting Gmail...")
print("   Opening browser for Gmail OAuth...")
try:
    gmail_conn = composio.connections.initiate(
        integration="GMAIL",
        entity_id=entity_id
    )
    print(f"   Visit: {gmail_conn.auth_url}")
    input("   Press Enter after authorizing in browser...")
    print("   ✓ Gmail connected")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Connect ElevenLabs
print("\n3. Connecting ElevenLabs...")
try:
    composio.connections.initiate(
        integration="ELEVENLABS",
        entity_id=entity_id,
        auth_config={"api_key": os.getenv("ELEVENLABS_API_KEY")}
    )
    print("   ✓ ElevenLabs connected")
except Exception as e:
    print(f"   ✗ Error: {e}")

# Verify
print("\nConnection Status:")
for conn in composio.connections.list(entity_id=entity_id):
    print(f"  {conn.integration}: {conn.status}")
```

Run it:

```bash
python setup_connections.py
```

---

## Step 4: Create Basic Agency (5 minutes)

Create `agency.py`:

```python
from agency_swarm import Agency, Agent
from composio import Composio
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize Composio
composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
entity_id = "default_user"

# Get tools
gmail_tools = composio.tools.get(toolkits=["GMAIL"], entity_id=entity_id)
telegram_tools = composio.tools.get(toolkits=["TELEGRAM"], entity_id=entity_id)
elevenlabs_tools = composio.tools.get(toolkits=["ELEVENLABS"], entity_id=entity_id)

# Create agents
telegram_agent = Agent(
    name="TelegramAgent",
    description="Handles Telegram messaging and user interactions",
    instructions="""
    You manage the Telegram interface.
    - Listen for incoming messages
    - Send responses to users
    - Handle voice message requests
    """,
    tools=telegram_tools
)

email_agent = Agent(
    name="EmailAgent",
    description="Manages Gmail drafts and email operations",
    instructions="""
    You handle all email operations.
    - Create email drafts
    - Read existing drafts
    - Send emails after approval
    - Update drafts based on feedback
    """,
    tools=gmail_tools
)

voice_agent = Agent(
    name="VoiceAgent",
    description="Converts text to speech using ElevenLabs",
    instructions="""
    You handle voice synthesis.
    - Convert email drafts to speech
    - Send voice messages via Telegram
    - Use natural, professional voice
    """,
    tools=elevenlabs_tools
)

# Create agency
agency = Agency(
    agents=[
        telegram_agent,
        [telegram_agent, email_agent],
        [telegram_agent, voice_agent],
        [email_agent, voice_agent]
    ],
    shared_instructions="""
    You are a voice-first email draft approval system.

    Workflow:
    1. User requests email draft via Telegram
    2. EmailAgent creates the draft
    3. VoiceAgent reads draft aloud
    4. TelegramAgent sends voice to user via Telegram
    5. User approves/modifies
    6. EmailAgent sends final email

    Always be professional and clear.
    """,
    temperature=0.5,
    max_prompt_tokens=4000
)

if __name__ == "__main__":
    # Run with Gradio interface
    agency.demo_gradio(height=600)
```

---

## Step 5: Run the System (1 minute)

```bash
python agency.py
```

This opens a web interface at http://localhost:7860

---

## Testing Your Setup

### Test 1: Telegram Connection

In the Gradio interface, try:
```
Send a message "Hello" to my Telegram bot
```

Check your Telegram app - you should receive the message.

### Test 2: Email Draft

```
Create an email draft to test@example.com with subject "Test" and body "This is a test"
```

Check Gmail drafts - should see the draft.

### Test 3: Voice Synthesis

```
Convert this text to speech: "This is a test of the voice system"
```

Should receive audio output.

### Test 4: Complete Workflow

```
I need to send an email to john@example.com about the project update.
Draft it, read it to me, and wait for my approval.
```

---

## Troubleshooting

### Error: "COMPOSIO_API_KEY not found"

```bash
# Check .env file
cat .env | grep COMPOSIO_API_KEY

# If missing, add it
echo "COMPOSIO_API_KEY=comp_your-key" >> .env
```

### Error: "Connection not active"

```bash
# Re-run setup
python setup_connections.py
```

### Telegram Bot Not Responding

1. Check bot token is correct
2. Verify bot is not blocked
3. Test bot directly: Send `/start` to your bot in Telegram

### Gmail OAuth Issues

1. Ensure Gmail API is enabled in Google Cloud Console
2. Add your email as test user
3. Use incognito browser for OAuth

### Import Errors

```bash
# Reinstall packages
pip install --upgrade agency-swarm composio-openai
```

---

## Next Steps

### 1. Enhance the System

- Add more sophisticated email templates
- Implement approval workflow with buttons
- Add email scheduling
- Integrate calendar for meeting emails

### 2. Production Deployment

- Set up proper webhook for Telegram
- Deploy to cloud (Heroku, AWS, etc.)
- Add error logging
- Implement rate limiting

### 3. Advanced Features

- Voice commands via Telegram voice messages
- Multi-language support
- Email categorization
- Smart reply suggestions

---

## File Structure

Your project should look like:

```
voice-email-telegram/
├── .env                    # API keys (DON'T COMMIT!)
├── .gitignore              # Ignore .env and venv
├── agency.py               # Main agency code
├── setup_connections.py    # Connection setup script
├── requirements.txt        # Dependencies
└── venv/                   # Virtual environment
```

Create `requirements.txt`:

```
agency-swarm>=0.2.0
composio-openai>=0.5.0
python-dotenv>=1.0.0
openai>=1.0.0
```

Create `.gitignore`:

```
.env
venv/
__pycache__/
*.pyc
.DS_Store
*.log
```

---

## Cost Estimates

### Development/Testing (per month)
- OpenAI API: $5-10
- Composio: Free
- Telegram: Free
- Gmail: Free
- ElevenLabs: Free (10K chars)
- **Total: $5-10/month**

### Light Production (per month)
- OpenAI API: $20-50
- ElevenLabs: $5 (30K chars)
- Others: Free
- **Total: $25-55/month**

---

## Getting Help

### Documentation
- This guide: `QUICK_START.md`
- Full API docs: `API_INTEGRATION_GUIDE.md`
- Composio setup: `COMPOSIO_SETUP_GUIDE.md`

### Community
- Agency Swarm GitHub: https://github.com/VRSEN/agency-swarm
- Composio Discord: https://composio.dev/discord
- OpenAI Community: https://community.openai.com

### Common Issues
- Check all API keys are in `.env`
- Verify virtual environment is activated
- Ensure all connections are "active" status
- Test each service independently first

---

## Success Checklist

- [ ] All API keys obtained and saved in `.env`
- [ ] Dependencies installed successfully
- [ ] Composio connections active
- [ ] Telegram bot responding
- [ ] Gmail drafts working
- [ ] Voice synthesis functional
- [ ] Agency running in Gradio
- [ ] Complete workflow tested

**Congratulations!** Your voice-first email system is ready.

---

## What You Built

You now have a working system that:

1. **Receives requests** via Telegram
2. **Creates email drafts** in Gmail
3. **Reads drafts aloud** using ElevenLabs
4. **Sends voice messages** via Telegram
5. **Handles approvals** and modifications
6. **Sends final emails** through Gmail

This demonstrates:
- Multi-agent coordination (Agency Swarm)
- External tool integration (Composio)
- OAuth authentication (Gmail)
- API key management (secure .env)
- Voice AI (ElevenLabs)
- Messaging platforms (Telegram)

**Next**: Customize for your specific use case and deploy to production!
