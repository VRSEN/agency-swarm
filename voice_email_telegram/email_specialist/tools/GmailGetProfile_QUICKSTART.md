# GmailGetProfile - Quick Start Guide

**Get up and running in 5 minutes**

---

## Prerequisites

```bash
# Ensure you have Python 3.9+ installed
python --version

# Install required packages
pip install composio-core agency-swarm python-dotenv pydantic
```

---

## Setup (5 Steps)

### Step 1: Connect Gmail via Composio

```bash
# Login to Composio and connect Gmail
composio add gmail
```

This will:
1. Open browser for Gmail authentication
2. Request necessary permissions
3. Create a connected entity

### Step 2: Get Your Entity ID

```bash
# List all connections
composio connections list

# Look for Gmail connection and copy the entity ID
# Example output:
# gmail | default | entity_123abc | ACTIVE
```

### Step 3: Configure Environment

```bash
# Create .env file in your project root
cat > .env << EOF
COMPOSIO_API_KEY=your_composio_api_key_here
GMAIL_ENTITY_ID=your_gmail_entity_id_here
EOF
```

**Get API Key**: https://app.composio.dev/settings/api-keys

### Step 4: Copy Tool to Your Project

```bash
# Copy GmailGetProfile.py to your email_specialist/tools/ directory
cp GmailGetProfile.py /path/to/your/email_specialist/tools/
```

### Step 5: Test It!

```bash
# Run standalone test
python GmailGetProfile.py
```

**Expected Output**:
```json
{
  "success": true,
  "email_address": "your.email@gmail.com",
  "messages_total": 15234,
  "threads_total": 8942,
  "history_id": "1234567890",
  "messages_per_thread": 1.70,
  "profile_summary": "your.email@gmail.com has 15234 messages in 8942 threads",
  "user_id": "me"
}
```

---

## Basic Usage

### Python Script

```python
from email_specialist.tools.GmailGetProfile import GmailGetProfile
import json

# Get Gmail profile
tool = GmailGetProfile()
result = json.loads(tool.run())

if result["success"]:
    print(f"Email: {result['email_address']}")
    print(f"Messages: {result['messages_total']:,}")
    print(f"Threads: {result['threads_total']:,}")
else:
    print(f"Error: {result['error']}")
```

### Agency Swarm Agent

```python
from agency_swarm import Agent
from email_specialist.tools.GmailGetProfile import GmailGetProfile

email_agent = Agent(
    name="Email Specialist",
    description="Handles Gmail profile operations",
    tools=[GmailGetProfile],
    temperature=0.5
)

# Ask agent
response = email_agent.get_completion("What's my Gmail address?")
print(response)
```

---

## Common Commands

### Get Email Address
```python
tool = GmailGetProfile()
result = json.loads(tool.run())
email = result.get("email_address")
```

### Check Message Count
```python
tool = GmailGetProfile()
result = json.loads(tool.run())
count = result.get("messages_total")
print(f"You have {count:,} emails")
```

### Get Full Profile
```python
tool = GmailGetProfile()
result = json.loads(tool.run())
print(result.get("profile_summary"))
```

---

## Troubleshooting

### Problem: "Missing Composio credentials"

**Solution**:
```bash
# Check .env file exists
cat .env

# Verify contents
COMPOSIO_API_KEY=your_key_here
GMAIL_ENTITY_ID=your_entity_here

# Load environment in Python
from dotenv import load_dotenv
load_dotenv()
```

### Problem: "Invalid API key"

**Solution**:
1. Go to https://app.composio.dev/settings/api-keys
2. Create new API key
3. Update `.env` file with new key

### Problem: "Gmail not connected"

**Solution**:
```bash
# Reconnect Gmail
composio add gmail

# Verify connection
composio connections list
```

---

## Next Steps

### Test Suite
```bash
# Run comprehensive tests
python test_gmail_get_profile.py
```

### Documentation
- **Full Documentation**: `GmailGetProfile_README.md`
- **Integration Guide**: `GmailGetProfile_INTEGRATION.md`
- **Summary**: `GmailGetProfile_SUMMARY.md`

### Integration Examples
- Agency Swarm multi-agent systems
- Voice assistants (ElevenLabs, Telegram)
- Web dashboards (Streamlit, Flask)
- Monitoring and automation

---

## Support

- **Pattern Reference**: `FINAL_VALIDATION_SUMMARY.md`
- **Composio Docs**: https://docs.composio.dev
- **Gmail API**: https://developers.google.com/gmail/api

---

**Ready to use!** 🚀

Total setup time: ~5 minutes
Lines of code needed: ~5 lines for basic usage
