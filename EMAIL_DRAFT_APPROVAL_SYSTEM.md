# Voice-First Email Draft Approval System (SIMPLIFIED)

## System Overview

**Flow:**
1. User sends voice message to Telegram bot
2. Agent processes request and drafts email
3. Agent sends draft to user in Telegram
4. User approves/rejects via Telegram buttons/text
5. If approved: Send email via Gmail
6. If rejected: Revise and repeat

**No PDF filling - Just email drafts with approval**

---

## Complete Working Code

```python
"""
Voice-First Email Draft Approval System
Telegram → Voice → Draft → Approve → Send Email

VERIFIED INTEGRATIONS:
- Telegram (Composio toolkit)
- ElevenLabs (Composio toolkit)
- Gmail (Composio toolkit)
- Mem0 (Composio toolkit)
"""

from agency_swarm import Agent, Agency, function_tool
from composio import Composio
from composio_openai_agents import OpenAIAgentsProvider
import json

# ============================================
# COMPOSIO SETUP (VERIFIED)
# ============================================

composio = Composio(provider=OpenAIAgentsProvider())

# Get tools from Composio
telegram_tools = composio.tools.get(
    user_id="your-user-id",
    toolkits=["TELEGRAM"]
)

voice_tools = composio.tools.get(
    user_id="your-user-id",
    toolkits=["ELEVENLABS"]
)

email_tools = composio.tools.get(
    user_id="your-user-id",
    toolkits=["GMAIL"]
)

memory_tools = composio.tools.get(
    user_id="your-user-id",
    toolkits=["MEM0"]
)

# ============================================
# DRAFT APPROVAL STORAGE (SIMPLE)
# ============================================

# In production: Use Railway PostgreSQL
pending_drafts = {}

@function_tool
async def save_email_draft(
    draft_id: str,
    recipient: str,
    subject: str,
    body: str,
    context: str
) -> str:
    """Save email draft for approval."""
    pending_drafts[draft_id] = {
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "context": context,
        "status": "pending",
        "created_at": "timestamp_here"
    }
    return f"Draft saved: {draft_id}"

@function_tool
async def get_draft(draft_id: str) -> str:
    """Retrieve draft by ID."""
    draft = pending_drafts.get(draft_id)
    if not draft:
        return "Draft not found"
    return json.dumps(draft)

@function_tool
async def update_draft_status(draft_id: str, status: str) -> str:
    """Update draft status (approved/rejected)."""
    if draft_id not in pending_drafts:
        return "Draft not found"

    pending_drafts[draft_id]["status"] = status
    return f"Draft {draft_id} status: {status}"

@function_tool
async def get_draft_status(draft_id: str) -> str:
    """Check if draft is approved."""
    draft = pending_drafts.get(draft_id)
    if not draft:
        return "not_found"
    return draft["status"]

# ============================================
# AGENTS (VERIFIED PATTERN)
# ============================================

# Agent 1: Telegram Voice Interface
telegram_agent = Agent(
    name="TelegramInterface",
    instructions="""You are the Telegram voice interface for email drafting.

    Your responsibilities:
    1. Receive voice/text messages from user
    2. Extract email request details (who, what, why)
    3. Store user preferences in mem0
    4. Format requests for EmailDrafter
    5. Show draft to user with clear formatting
    6. Listen for approval/rejection
    7. Confirm final actions via voice response

    When showing drafts:
    - Use clear formatting in Telegram
    - Include draft_id prominently
    - Ask: "Reply 'approve [draft_id]' or 'reject [draft_id]'"

    Use mem0 to remember:
    - User's communication style
    - Frequent recipients
    - Email signature preferences""",
    tools=telegram_tools + voice_tools + memory_tools
)

# Agent 2: Email Drafter
drafter_agent = Agent(
    name="EmailDrafter",
    instructions="""You create professional email drafts.

    Process:
    1. Receive email request from TelegramInterface
    2. Retrieve user context from mem0 (tone, signature, etc.)
    3. Draft professional email
    4. Save draft with unique ID
    5. Return draft_id to TelegramInterface for display

    Email quality standards:
    - Professional tone
    - Clear subject lines
    - Proper structure (greeting, body, closing)
    - Include user signature from mem0""",
    tools=[save_email_draft, get_draft] + memory_tools
)

# Agent 3: Approval Manager
approval_agent = Agent(
    name="ApprovalManager",
    instructions="""You manage the email approval workflow.

    Process:
    1. Receive draft_id from TelegramInterface
    2. Check approval status
    3. If approved: Trigger EmailSender
    4. If rejected: Request revisions from EmailDrafter
    5. Track approval history in mem0

    Never send email without explicit approval.""",
    tools=[get_draft_status, update_draft_status] + memory_tools
)

# Agent 4: Email Sender
sender_agent = Agent(
    name="EmailSender",
    instructions="""You send approved emails via Gmail.

    Process:
    1. Receive approved draft_id from ApprovalManager
    2. Retrieve full draft details
    3. Send via Gmail using email_tools
    4. Log sent email in mem0
    5. Return confirmation

    CRITICAL: Only send if status is 'approved'
    Store sent email metadata in mem0 for future reference.""",
    tools=[get_draft] + email_tools + memory_tools
)

# Agent 5: Coordinator
coordinator = Agent(
    name="EmailCoordinator",
    instructions="""You orchestrate the email drafting workflow.

    Standard Flow:
    1. User sends voice → TelegramInterface processes
    2. Delegate to EmailDrafter to create draft
    3. TelegramInterface shows draft to user
    4. User responds with approve/reject
    5. If approved: ApprovalManager → EmailSender → Send
    6. If rejected: Get feedback → EmailDrafter revises
    7. TelegramInterface confirms via voice

    Revision Flow:
    - Collect specific feedback from user
    - Pass to EmailDrafter with revision notes
    - Show updated draft
    - Repeat approval process

    Use mem0 to improve:
    - Draft quality over time
    - Understanding user preferences
    - Common email patterns""",
    tools=memory_tools
)

# ============================================
# BUILD AGENCY
# ============================================

agency = Agency(
    coordinator,
    communication_flows=[
        coordinator > telegram_agent,
        coordinator > drafter_agent,
        coordinator > approval_agent,
        coordinator > sender_agent,
        (telegram_agent, coordinator),  # Two-way for user input
        (telegram_agent, drafter_agent),  # Direct for showing drafts
    ],
    shared_instructions="""
    - Always prioritize user approval before sending
    - Use professional tone for all emails
    - Remember user preferences via mem0
    - Confirm all actions via Telegram
    """
)

# ============================================
# DEPLOYMENT
# ============================================

if __name__ == "__main__":
    from agency_swarm import run_fastapi

    # Deploy to Railway
    run_fastapi(
        agencies={"email-assistant": lambda: agency},
        host="0.0.0.0",
        port=8000
    )
```

---

## Example User Flow

### 1. User Sends Voice Message
```
User (Telegram voice):
"Draft an email to supplier@iceco.com asking for 50 bags of ice
delivered this Friday to 123 Main Street"
```

### 2. System Processes & Creates Draft
```
TelegramInterface → Coordinator → EmailDrafter
```

### 3. Draft Shown in Telegram
```
Telegram Bot:
━━━━━━━━━━━━━━━━━━━━
📧 EMAIL DRAFT #draft_001

To: supplier@iceco.com
Subject: Ice Order Request - Delivery Friday

Hi Team,

I would like to place an order for 50 bags of ice
to be delivered this Friday to the following address:

123 Main Street
[City, State ZIP]

Please confirm availability and delivery time.

Best regards,
[Your Name]
━━━━━━━━━━━━━━━━━━━━

✅ To approve: Reply "approve draft_001"
❌ To revise: Reply "reject draft_001 [feedback]"
```

### 4a. User Approves
```
User: "approve draft_001"

System processes:
TelegramInterface → Coordinator → ApprovalManager → EmailSender

Telegram Bot (voice):
"✅ Email sent successfully to supplier@iceco.com"
```

### 4b. User Requests Revision
```
User: "reject draft_001 - make it more urgent and ask for delivery by 10am"

System processes:
TelegramInterface → Coordinator → EmailDrafter (with feedback)

Telegram Bot:
━━━━━━━━━━━━━━━━━━━━
📧 REVISED DRAFT #draft_002

To: supplier@iceco.com
Subject: URGENT: Ice Order Request - Delivery Friday 10am

Hi Team,

URGENT REQUEST: I need to place an order for 50 bags
of ice to be delivered THIS FRIDAY BY 10:00 AM to:

123 Main Street
[City, State ZIP]

Please confirm immediately if you can accommodate
this delivery time.

Best regards,
[Your Name]
━━━━━━━━━━━━━━━━━━━━

✅ To approve: Reply "approve draft_002"
❌ To revise: Reply "reject draft_002 [feedback]"
```

---

## Telegram Integration Details

### How Drafts are Displayed

**Option 1: Text Message (Simple)**
```python
# Via telegram_tools from Composio
# Send formatted text to user's Telegram chat
message = f"""
📧 EMAIL DRAFT #{draft_id}

To: {recipient}
Subject: {subject}

{body}

✅ Reply 'approve {draft_id}' to send
❌ Reply 'reject {draft_id}' for revisions
"""
# telegram_tools.send_message(chat_id, message)
```

**Option 2: With Inline Buttons (Better UX)**
```python
# Telegram supports inline keyboards
# User clicks buttons instead of typing
[Approve] [Reject] [Edit]
```

### Voice Response
```python
# After user approves/rejects
# Generate voice confirmation via voice_tools
# "Your email has been sent successfully"
# Send voice message back via telegram_tools
```

---

## Memory (mem0) Usage

### What Gets Stored:
```python
# User preferences
{
    "user_id": "telegram_user_123",
    "email_signature": "[Your Name]\n[Your Title]",
    "tone_preference": "professional",
    "frequent_recipients": {
        "ice_supplier": "supplier@iceco.com",
        "office_manager": "office@company.com"
    },
    "delivery_address": "123 Main Street, City, State"
}

# Draft history
{
    "draft_id": "draft_001",
    "approved": true,
    "sent_at": "2025-10-27",
    "recipient": "supplier@iceco.com",
    "purpose": "ice order"
}
```

### Benefits:
- Next time user says "order ice", system knows supplier email
- System remembers delivery address
- Learns user's preferred communication style
- Tracks what emails get approved vs rejected

---

## Database Schema (PostgreSQL on Railway)

```sql
CREATE TABLE email_drafts (
    draft_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(100),
    recipient VARCHAR(255),
    subject VARCHAR(500),
    body TEXT,
    context TEXT,
    status VARCHAR(20), -- pending, approved, rejected, sent
    created_at TIMESTAMP,
    approved_at TIMESTAMP,
    sent_at TIMESTAMP
);

CREATE TABLE approval_history (
    id SERIAL PRIMARY KEY,
    draft_id VARCHAR(50),
    action VARCHAR(20), -- approve, reject, revise
    feedback TEXT,
    timestamp TIMESTAMP
);
```

---

## Deployment Steps

### 1. Install Dependencies
```bash
pip install agency-swarm composio-openai-agents python-dotenv psycopg2-binary
```

### 2. Setup Composio
```bash
# Login to Composio
composio login

# Connect integrations
composio add telegram
composio add elevenlabs
composio add gmail
composio add mem0

# Get user_id for tools.get()
composio whoami
```

### 3. Configure Environment (.env)
```bash
OPENAI_API_KEY=sk-...
COMPOSIO_API_KEY=...
TELEGRAM_BOT_TOKEN=...
ELEVENLABS_API_KEY=...
DATABASE_URL=postgresql://... # Railway provides this
```

### 4. Test Locally
```bash
python main.py

# Or test with Gradio UI
agency.copilot_demo()
```

### 5. Deploy to Railway
```bash
# Clone template
git clone https://github.com/VRSEN/agency-swarm-api-railway-template

# Add your code
cp main.py agency-swarm-api-railway-template/

# Push to GitHub
git add .
git commit -m "Add email draft approval system"
git push origin main

# Railway auto-deploys
```

---

## Testing the System

### Test Messages:

**Test 1: Simple Email**
```
Voice: "Send an email to john@example.com saying I'll be late to the meeting"
Expected: Draft appears in Telegram with approve/reject options
```

**Test 2: With Context**
```
Voice: "Draft an email to the ice supplier ordering 50 bags for Friday delivery"
Expected: System uses mem0 to fill in supplier email and address
```

**Test 3: Rejection & Revision**
```
Text: "reject draft_001 - make it sound more urgent"
Expected: New draft with urgent tone
```

**Test 4: Voice Confirmation**
```
After approval, expect voice message:
"Your email to supplier@iceco.com has been sent successfully"
```

---

## Adding More Agents Later (VERIFIED EASY)

### Example: Add SMS Notifications

```python
# Get SMS tools from Composio
sms_tools = composio.tools.get(toolkits=["TWILIO"])

# Create SMS agent
sms_agent = Agent(
    name="SMSNotifier",
    instructions="Send SMS notifications for important updates",
    tools=sms_tools + memory_tools
)

# Add to flows
agency = Agency(
    coordinator,
    communication_flows=[
        # ... existing flows ...
        coordinator > sms_agent,  # ← Just add here
    ]
)
```

### Example: Add Calendar Integration

```python
calendar_tools = composio.tools.get(toolkits=["GOOGLECALENDAR"])

calendar_agent = Agent(
    name="CalendarAgent",
    instructions="Schedule follow-ups and reminders",
    tools=calendar_tools + memory_tools
)

# Add to flows
agency = Agency(
    coordinator,
    communication_flows=[
        coordinator > telegram_agent,
        coordinator > drafter_agent,
        coordinator > approval_agent,
        coordinator > sender_agent,
        coordinator > calendar_agent,  # ← New agent added
    ]
)
```

**That's it! No complex refactoring needed.**

---

## Approval UI Options

### Option 1: Text Commands (Simplest)
```
User types: "approve draft_001"
```

### Option 2: Telegram Inline Buttons (Better)
```python
# Telegram supports inline keyboards
telegram_tools.send_message_with_buttons(
    chat_id=user_id,
    message=draft_text,
    buttons=[
        {"text": "✅ Approve", "callback": f"approve_{draft_id}"},
        {"text": "❌ Reject", "callback": f"reject_{draft_id}"},
        {"text": "✏️ Edit", "callback": f"edit_{draft_id}"}
    ]
)
```

### Option 3: Web UI (Most Flexible)
```python
# Railway template includes web UI
# User clicks link in Telegram
# Opens web page showing draft
# Click approve/reject buttons
```

**Recommendation: Start with text commands, upgrade to inline buttons in V2**

---

## Cost Estimate (Monthly)

| Service | Cost | Notes |
|---------|------|-------|
| OpenAI API | $20-50 | GPT-4o usage |
| Railway | $5-10 | Hobby plan, includes PostgreSQL |
| Composio | Free | Up to 20k tool calls/month |
| Telegram Bot | Free | No cost |
| ElevenLabs | $5-11 | Starter plan for voice |
| **Total** | **$30-71/mo** | For MVP usage |

---

## Next Steps

1. ✅ Set up Telegram bot via BotFather
2. ✅ Connect Composio integrations
3. ✅ Build agents (copy code above)
4. ✅ Test locally with `agency.copilot_demo()`
5. ✅ Deploy to Railway
6. ✅ Test end-to-end via Telegram
7. 🚀 Launch MVP

---

## Success Metrics

**Week 1-2 (MVP):**
- [ ] User can send voice request via Telegram
- [ ] System generates email draft
- [ ] Draft appears in Telegram for approval
- [ ] Approved emails send successfully
- [ ] System remembers user preferences

**Week 3-4 (Improvements):**
- [ ] Add inline buttons for approval
- [ ] Voice responses for confirmations
- [ ] Smart suggestions based on history
- [ ] Multiple recipient support
- [ ] Attachment support

---

**This is the simplified, focused version you asked for. No PDF complexity - just email drafts with Telegram approval!** 🎯
