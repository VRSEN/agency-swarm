# How to Build This in Claude Code - Step by Step

## START HERE: Project Setup

### Step 1: Create Project Directory

```bash
# Navigate to where you want your project
cd ~/projects  # or wherever

# Create project
mkdir email-assistant
cd email-assistant

# Initialize git
git init
git branch -M main
```

### Step 2: Create Project Structure

```bash
# Create directories
mkdir -p agents/telegram_interface
mkdir -p agents/email_drafter
mkdir -p agents/approval_manager
mkdir -p agents/email_sender
mkdir -p agents/coordinator
mkdir -p tools
mkdir -p config

# Create files
touch main.py
touch requirements.txt
touch .env
touch .gitignore
touch README.md
```

Your structure should look like:
```
email-assistant/
├── main.py                 # Main entry point
├── requirements.txt        # Dependencies
├── .env                    # API keys (DON'T COMMIT)
├── .gitignore             # Git ignore
├── README.md              # Documentation
├── agents/                # Agent definitions
│   ├── telegram_interface/
│   ├── email_drafter/
│   ├── approval_manager/
│   ├── email_sender/
│   └── coordinator/
├── tools/                 # Custom tools
│   ├── __init__.py
│   ├── draft_tools.py
│   └── approval_tools.py
└── config/               # Configuration
    └── settings.py
```

---

## Step 3: Set Up Dependencies

**File: `requirements.txt`**
```txt
agency-swarm>=1.0.0
composio-openai-agents
python-dotenv
psycopg2-binary
pydantic
```

**Install:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## Step 4: Configure Environment Variables

**File: `.env`**
```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Composio
COMPOSIO_API_KEY=...

# Telegram
TELEGRAM_BOT_TOKEN=...

# ElevenLabs
ELEVENLABS_API_KEY=...

# Database (for production)
DATABASE_URL=postgresql://...
```

**File: `.gitignore`**
```
.env
venv/
__pycache__/
*.pyc
.DS_Store
*.db
```

---

## Step 5: Setup Composio

```bash
# Install Composio CLI
pip install composio-core

# Login
composio login

# Add integrations
composio add telegram
composio add elevenlabs
composio add gmail
composio add mem0

# Get your user ID
composio whoami
# Copy the user_id - you'll need this
```

---

## Step 6: Create Custom Tools

**File: `tools/draft_tools.py`**
```python
"""Custom tools for draft management."""
from agency_swarm import function_tool
from datetime import datetime

# In-memory storage (use PostgreSQL in production)
pending_drafts = {}

@function_tool
async def save_email_draft(
    draft_id: str,
    recipient: str,
    subject: str,
    body: str,
    user_id: str
) -> str:
    """Save email draft for approval.

    Args:
        draft_id: Unique draft identifier
        recipient: Email recipient
        subject: Email subject line
        body: Email body content
        user_id: Telegram user ID

    Returns:
        Confirmation message
    """
    pending_drafts[draft_id] = {
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "user_id": user_id,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    return f"✅ Draft {draft_id} saved successfully"

@function_tool
async def get_draft(draft_id: str) -> str:
    """Retrieve draft by ID.

    Args:
        draft_id: Draft identifier

    Returns:
        Draft details as formatted string
    """
    draft = pending_drafts.get(draft_id)
    if not draft:
        return "❌ Draft not found"

    return f"""
    Draft ID: {draft_id}
    To: {draft['recipient']}
    Subject: {draft['subject']}
    Status: {draft['status']}

    Body:
    {draft['body']}
    """

@function_tool
async def get_draft_status(draft_id: str) -> str:
    """Check draft approval status.

    Args:
        draft_id: Draft identifier

    Returns:
        Status: pending, approved, or rejected
    """
    draft = pending_drafts.get(draft_id)
    if not draft:
        return "not_found"
    return draft["status"]

@function_tool
async def update_draft_status(draft_id: str, status: str) -> str:
    """Update draft approval status.

    Args:
        draft_id: Draft identifier
        status: New status (approved/rejected)

    Returns:
        Confirmation message
    """
    if draft_id not in pending_drafts:
        return "❌ Draft not found"

    pending_drafts[draft_id]["status"] = status
    return f"✅ Draft {draft_id} marked as {status}"
```

**File: `tools/__init__.py`**
```python
"""Custom tools package."""
from .draft_tools import (
    save_email_draft,
    get_draft,
    get_draft_status,
    update_draft_status
)

__all__ = [
    "save_email_draft",
    "get_draft",
    "get_draft_status",
    "update_draft_status"
]
```

---

## Step 7: Create Agent Definitions

**File: `agents/telegram_interface/instructions.md`**
```markdown
# Telegram Interface Agent

You are the voice and text interface for the email assistant.

## Responsibilities

1. **Receive Input**
   - Accept voice messages (Telegram auto-transcribes)
   - Accept text messages
   - Extract email intent (who, what, when)

2. **Show Drafts**
   - Format drafts clearly with draft_id
   - Include approve/reject instructions
   - Use emoji for visual clarity

3. **Handle Responses**
   - Parse "approve draft_XXX" commands
   - Parse "reject draft_XXX [feedback]" commands
   - Extract revision feedback

4. **Send Confirmations**
   - Voice confirmations for important actions
   - Text confirmations for acknowledgments
   - Error messages when things fail

## Communication Style

- Professional but friendly
- Use clear formatting
- Always include draft_id prominently
- Confirm actions explicitly

## Memory Usage

Use mem0 to remember:
- User's email signature
- Frequent recipients
- Preferred communication tone
- Common email patterns
```

**File: `agents/email_drafter/instructions.md`**
```markdown
# Email Drafter Agent

You create professional email drafts based on user requests.

## Process

1. **Receive Request**
   - Get email intent from Coordinator
   - Note recipient, purpose, urgency

2. **Retrieve Context**
   - Query mem0 for user preferences
   - Get email signature
   - Get communication tone
   - Check if recipient is frequent contact

3. **Draft Email**
   - Professional structure
   - Clear subject line
   - Proper greeting and closing
   - Include signature from mem0

4. **Save Draft**
   - Generate unique draft_id
   - Save with save_email_draft tool
   - Return draft_id to Coordinator

## Email Quality Standards

- Subject: Clear, specific, under 60 chars
- Greeting: Match formality to context
- Body: Concise, actionable, well-structured
- Closing: Professional, include signature
- Tone: Match user preferences from mem0
```

**File: `agents/approval_manager/instructions.md`**
```markdown
# Approval Manager Agent

You manage the human approval workflow.

## Process

1. **Receive Approval Request**
   - Get draft_id from Coordinator
   - Check current status

2. **Monitor Status**
   - Poll status using get_draft_status
   - Wait for user to approve/reject
   - Timeout after reasonable period

3. **Route Based on Status**
   - If approved: Notify EmailSender
   - If rejected: Get feedback, notify Drafter
   - If timeout: Notify user via Telegram

4. **Track History**
   - Store approval decisions in mem0
   - Learn from rejected drafts
   - Improve future suggestions

## Rules

- NEVER send email without explicit approval
- Always verify status before triggering send
- Log all approval decisions
- Respect user preferences for notifications
```

**File: `agents/email_sender/instructions.md`**
```markdown
# Email Sender Agent

You send approved emails via Gmail.

## Process

1. **Verify Approval**
   - Check draft_status = "approved"
   - Reject if not approved

2. **Retrieve Draft**
   - Get full draft details with get_draft
   - Verify all fields present

3. **Send Email**
   - Use Gmail tools from Composio
   - Send to recipient
   - Handle errors gracefully

4. **Confirm & Log**
   - Store sent email in mem0
   - Return confirmation to Coordinator
   - Include timestamp and recipient

## Safety Rules

- Double-check approval status
- Validate email addresses
- Handle API errors
- Never send without approval
- Log all sent emails for audit
```

**File: `agents/coordinator/instructions.md`**
```markdown
# Coordinator Agent

You orchestrate the entire email drafting workflow.

## Standard Flow

1. **Receive User Request** (from TelegramInterface)
   - Parse intent
   - Identify type of email
   - Check if urgent

2. **Draft Creation**
   - Delegate to EmailDrafter
   - Receive draft_id
   - Pass to TelegramInterface for display

3. **Approval Process**
   - Wait for user response via TelegramInterface
   - Delegate to ApprovalManager
   - Monitor status

4. **Send or Revise**
   - If approved: Delegate to EmailSender
   - If rejected: Loop back to EmailDrafter with feedback

5. **Confirm Completion**
   - Notify user via TelegramInterface
   - Store interaction in mem0

## Revision Flow

If user rejects:
1. Parse feedback from user response
2. Pass original draft + feedback to EmailDrafter
3. Get new draft_id
4. Show new draft to user
5. Repeat approval process

## Context Management

- Use mem0 to improve over time
- Track successful patterns
- Learn user preferences
- Optimize draft quality
```

---

## Step 8: Build Main Application

**File: `main.py`**
```python
"""
Email Draft Approval System - Main Application
Voice-first email assistant with Telegram approval
"""

import os
from dotenv import load_dotenv
from composio import Composio
from composio_openai_agents import OpenAIAgentsProvider
from agency_swarm import Agent, Agency

# Import custom tools
from tools import (
    save_email_draft,
    get_draft,
    get_draft_status,
    update_draft_status
)

# Load environment variables
load_dotenv()

# Verify required env vars
required_vars = ["OPENAI_API_KEY", "COMPOSIO_API_KEY"]
for var in required_vars:
    if not os.getenv(var):
        raise ValueError(f"Missing required environment variable: {var}")

# Initialize Composio
composio = Composio(provider=OpenAIAgentsProvider())
user_id = os.getenv("COMPOSIO_USER_ID", "default_user")

# Get Composio tools
print("Loading Composio toolkits...")
telegram_tools = composio.tools.get(user_id=user_id, toolkits=["TELEGRAM"])
voice_tools = composio.tools.get(user_id=user_id, toolkits=["ELEVENLABS"])
email_tools = composio.tools.get(user_id=user_id, toolkits=["GMAIL"])
memory_tools = composio.tools.get(user_id=user_id, toolkits=["MEM0"])

print("✅ Toolkits loaded successfully")

# Define Agents
print("Creating agents...")

telegram_agent = Agent(
    name="TelegramInterface",
    instructions="./agents/telegram_interface/instructions.md",
    tools=telegram_tools + voice_tools + memory_tools,
)

drafter_agent = Agent(
    name="EmailDrafter",
    instructions="./agents/email_drafter/instructions.md",
    tools=[save_email_draft, get_draft] + memory_tools,
)

approval_agent = Agent(
    name="ApprovalManager",
    instructions="./agents/approval_manager/instructions.md",
    tools=[get_draft_status, update_draft_status] + memory_tools,
)

sender_agent = Agent(
    name="EmailSender",
    instructions="./agents/email_sender/instructions.md",
    tools=[get_draft] + email_tools + memory_tools,
)

coordinator = Agent(
    name="Coordinator",
    instructions="./agents/coordinator/instructions.md",
    tools=memory_tools,
)

print("✅ Agents created")

# Build Agency
print("Building agency...")

agency = Agency(
    coordinator,  # Entry point
    communication_flows=[
        coordinator > telegram_agent,
        coordinator > drafter_agent,
        coordinator > approval_agent,
        coordinator > sender_agent,
        (telegram_agent, coordinator),  # Two-way communication
    ],
    shared_instructions="""
    - Always prioritize user approval before sending emails
    - Use professional tone for all communications
    - Remember user preferences via mem0
    - Confirm all important actions
    - Handle errors gracefully with clear messages
    """
)

print("✅ Agency built successfully")

# Run Application
if __name__ == "__main__":
    print("\n" + "="*50)
    print("EMAIL DRAFT APPROVAL SYSTEM")
    print("="*50 + "\n")

    # For development: Use Gradio UI
    print("Starting Gradio demo interface...")
    print("Open the URL below in your browser:\n")
    agency.copilot_demo()

    # For production: Use FastAPI
    # from agency_swarm import run_fastapi
    # run_fastapi(
    #     agencies={"email-assistant": lambda: agency},
    #     host="0.0.0.0",
    #     port=8000
    # )
```

---

## Step 9: Test Locally

```bash
# Run the application
python main.py

# You'll see:
# Loading Composio toolkits...
# ✅ Toolkits loaded successfully
# Creating agents...
# ✅ Agents created
# Building agency...
# ✅ Agency built successfully
# Starting Gradio demo interface...
# Running on local URL:  http://127.0.0.1:7860
```

Open the URL in your browser and test!

---

## Step 10: Test Queries

Try these in the Gradio UI:

**Test 1: Simple Email**
```
"Draft an email to john@example.com saying I'll be 10 minutes late to our meeting"
```

**Test 2: With Context**
```
"Email the ice supplier asking for 50 bags to be delivered Friday"
```

**Test 3: Approval**
```
"approve draft_001"
```

**Test 4: Rejection**
```
"reject draft_001 - make it sound more urgent and professional"
```

---

## Step 11: Deploy to Railway

### A. Prepare for Deployment

**Create: `Procfile`**
```
web: python main.py
```

**Update `main.py` for production:**
```python
if __name__ == "__main__":
    import sys

    if "--demo" in sys.argv:
        # Local development
        agency.copilot_demo()
    else:
        # Production deployment
        from agency_swarm import run_fastapi
        run_fastapi(
            agencies={"email-assistant": lambda: agency},
            host="0.0.0.0",
            port=int(os.getenv("PORT", 8000))
        )
```

### B. Deploy

```bash
# Clone Railway template
git clone https://github.com/VRSEN/agency-swarm-api-railway-template railway-deploy
cd railway-deploy

# Copy your code
cp -r ../email-assistant/* .

# Commit
git add .
git commit -m "Initial email assistant deployment"

# Push to GitHub
git remote add origin your-github-repo
git push -u origin main

# Connect to Railway
# Go to railway.app
# Create new project from GitHub repo
# Add environment variables in Railway dashboard
# Deploy!
```

---

## Common Issues & Solutions

### Issue: Composio authentication fails
```bash
# Re-authenticate
composio logout
composio login
composio add telegram
```

### Issue: Import errors
```bash
# Reinstall dependencies
pip uninstall agency-swarm composio-openai-agents
pip install --no-cache-dir agency-swarm composio-openai-agents
```

### Issue: Agents not communicating
- Check `communication_flows` - ensure paths exist
- Verify agent names match exactly
- Check logs for errors

### Issue: Tools not working
- Verify Composio toolkits are connected: `composio apps`
- Check API keys in `.env`
- Test individual tools in isolation

---

## Development Tips

### 1. Test Components Separately

```python
# Test a single tool
import asyncio
from tools import save_email_draft

async def test():
    result = await save_email_draft(
        draft_id="test_001",
        recipient="test@example.com",
        subject="Test",
        body="Test body",
        user_id="user123"
    )
    print(result)

asyncio.run(test())
```

### 2. Use Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 3. Start Simple, Add Complexity

Build in this order:
1. ✅ Basic agent structure (no tools)
2. ✅ Add draft storage tools
3. ✅ Add Composio tools
4. ✅ Add approval workflow
5. ✅ Add voice features
6. ✅ Deploy

### 4. Use Version Control

```bash
git add .
git commit -m "Add feature X"
git push
```

---

## Next Steps After MVP

1. **Add WhatsApp** - Just get WhatsApp tools from Composio
2. **Add Calendar** - Integrate Google Calendar for follow-ups
3. **Add SMS** - Use Twilio toolkit for notifications
4. **Improve UI** - Build React frontend
5. **Add Analytics** - Track usage patterns in mem0

Each new feature = new agent + add to communication_flows!

---

## Getting Help

- **Agency Swarm Docs:** https://agency-swarm.ai
- **Composio Docs:** https://docs.composio.dev
- **Railway Docs:** https://docs.railway.app
- **This repo issues:** Ask questions here

---

## Summary: How to Start

```bash
# 1. Create project
mkdir email-assistant && cd email-assistant

# 2. Setup
python -m venv venv
source venv/bin/activate
pip install agency-swarm composio-openai-agents python-dotenv

# 3. Configure
composio login
composio add telegram
composio add gmail
composio add elevenlabs
composio add mem0

# 4. Copy code from EMAIL_DRAFT_APPROVAL_SYSTEM.md

# 5. Test
python main.py

# 6. Deploy to Railway
```

**Start building NOW! 🚀**
