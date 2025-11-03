# Quick Start: Email Signature & Auto-Learning Contacts

**5-Minute Setup Guide** for email signature and contact learning features.

---

## ⚡ Quick Overview

Two new features are ready to use:

1. **Automatic Email Signature**: All emails automatically signed "Cheers, Ashley"
2. **Auto-Learn Contacts**: Extract contacts from emails, filter out newsletters

---

## 🚀 Setup (2 minutes)

### Prerequisites
Ensure these environment variables are set in `.env`:

```bash
# Required for email features
COMPOSIO_API_KEY=your_composio_api_key
GMAIL_CONNECTION_ID=your_gmail_connection_id

# Required for contact storage
MEM0_API_KEY=your_mem0_api_key
```

---

## 📧 Feature 1: Email Signature (30 seconds)

### No changes needed! It just works.

**Before** (manual):
```python
tool = GmailSendEmail(
    to="john@example.com",
    subject="Update",
    body="Thanks for the info.\n\nCheers, Ashley"  # Manual signature
)
```

**After** (automatic):
```python
tool = GmailSendEmail(
    to="john@example.com",
    subject="Update",
    body="Thanks for the info."  # Signature auto-added
)
# Email sent: "Thanks for the info.\n\nCheers, Ashley"
```

### Special Cases

**Skip signature for automated emails:**
```python
tool = GmailSendEmail(
    to="system@example.com",
    subject="Daily Report",
    body="Report attached.",
    skip_signature=True  # No signature
)
```

---

## 👥 Feature 2: Auto-Learn Contacts (1 minute)

### Basic Usage

```python
from memory_manager.tools.AutoLearnContactFromEmail import AutoLearnContactFromEmail
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
import json

# 1. Fetch emails
fetch = GmailFetchEmails(query="is:unread", max_results=10)
result = json.loads(fetch.run())

# 2. Learn contacts (skips newsletters automatically)
for email in result["messages"]:
    learn = AutoLearnContactFromEmail(
        email_data=email,
        user_id="ashley_user_123"
    )
    learn.run()
```

### What Happens Automatically

✅ **Real Person** → Contact learned and stored in Mem0
```
From: John Doe <john@acmecorp.com>
→ ✓ Learned: John Doe <john@acmecorp.com>
```

⊘ **Newsletter** → Automatically skipped
```
From: Marketing <noreply@company.com>
Headers: List-Unsubscribe
→ ⊘ Skipped: newsletter_detected
```

---

## 🧪 Test It (2 minutes)

### Test Email Signature
```bash
cd /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram
python tests/test_email_signature.py
```

**Expected**: 6/6 tests passed ✅

### Test Contact Learning
```bash
python tests/test_auto_learn_contacts.py
```

**Expected**: 9/9 tests passed ✅

### Run Example Workflow
```bash
python examples/email_workflow_example.py
```

**Expected**: Mock demonstration (shows what happens with real credentials)

---

## 🎯 Complete Workflow Example

### Process emails and send replies:

```python
import json
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
from email_specialist.tools.GmailSendEmail import GmailSendEmail
from memory_manager.tools.AutoLearnContactFromEmail import AutoLearnContactFromEmail

# 1. Fetch unread emails
fetch = GmailFetchEmails(query="is:unread", max_results=10)
emails = json.loads(fetch.run())["messages"]

# 2. Auto-learn contacts (newsletters filtered automatically)
for email in emails:
    learn = AutoLearnContactFromEmail(
        email_data=email,
        user_id="ashley_user_123"
    )
    result = json.loads(learn.run())

    if result.get("success") and not result.get("skipped"):
        print(f"✓ Learned: {result['contact']['name']}")
    elif result.get("skipped"):
        print(f"⊘ Skipped newsletter: {result.get('email')}")

# 3. Send reply (signature auto-added)
send = GmailSendEmail(
    to="john@acmecorp.com",
    subject="Re: Project Update",
    body="Thanks for the update!"
)
send.run()
# Sent with signature: "Thanks for the update!\n\nCheers, Ashley"
```

---

## 🔍 Newsletter Detection

**How it works**: Requires 2+ indicators to classify as newsletter

### Indicators Checked:
1. **Headers**: List-Unsubscribe, List-Id, Precedence: bulk
2. **From address**: noreply@, newsletter@, notifications@, etc.
3. **Body keywords**: "unsubscribe", "manage preferences", etc.

### Example Classification:

**Newsletter (2 indicators)**:
```
From: noreply@marketing.com  ← Indicator 1
Headers: List-Unsubscribe     ← Indicator 2
→ Classified as NEWSLETTER
```

**Real Email (1 indicator)**:
```
From: support@company.com
Body: "...manage your preferences..."  ← Only 1 indicator
→ NOT classified as newsletter (learned as contact)
```

---

## ⚙️ Configuration

### Change Signature Text

Edit `email_specialist/tools/GmailSendEmail.py`:

```python
def _append_signature(self, body: str) -> str:
    # Change this line:
    signature = "Cheers, Ashley"

    # To your preferred signature:
    signature = "Best regards,\nAshley Tower"
    # ...
```

### Adjust Newsletter Detection

Edit `memory_manager/tools/AutoLearnContactFromEmail.py`:

```python
def _is_newsletter(self, email_data: dict) -> tuple[bool, list[str]]:
    # ...

    # Change threshold (currently 2)
    is_newsletter = len(indicators) >= 2  # More strict: >= 3, Less strict: >= 1
    # ...
```

---

## 📊 What Gets Stored in Mem0

When a contact is learned:

```json
{
  "text": "Contact: John Doe, email: john@acmecorp.com",
  "user_id": "ashley_user_123",
  "metadata": {
    "type": "contact",
    "name": "John Doe",
    "email": "john@acmecorp.com",
    "source": "email_auto_learn",
    "learned_at": "2025-11-02T22:30:00.000Z",
    "subject": "Project Update",
    "date": "Sat, 2 Nov 2025 18:30:00 -0400",
    "force_added": false
  }
}
```

---

## 🐛 Troubleshooting

### Signature Not Appearing
**Problem**: Email sent without signature

**Solution**:
- Check `skip_signature` not set to `True`
- Verify body doesn't already contain "Cheers, Ashley"
- Check GmailSendEmail logs

### Newsletters Being Learned
**Problem**: Newsletter contacts in Mem0

**Solution**:
- Check newsletter has 2+ indicators (see test output)
- Adjust detection threshold if needed
- Add more patterns to `newsletter_patterns` list

### Contacts Not Being Learned
**Problem**: Real emails being skipped

**Solution**:
- Check if email has 2+ newsletter indicators
- Use `force_add=True` to override detection
- Review indicators in skip message

### Mem0 API Errors
**Problem**: "401 Unauthorized" or connection errors

**Solution**:
- Verify `MEM0_API_KEY` set in `.env`
- Check API key is valid at mem0.ai
- Ensure network connection to api.mem0.ai

---

## 📚 Full Documentation

For complete details, see:

- **EMAIL_SIGNATURE_AND_CONTACTS_GUIDE.md**: Complete usage guide, API reference, troubleshooting
- **IMPLEMENTATION_SUMMARY.md**: Technical details, test results, architecture
- **examples/email_workflow_example.py**: Working code examples

---

## ✅ Quick Checklist

Before using in production:

- [ ] `COMPOSIO_API_KEY` set in `.env`
- [ ] `GMAIL_CONNECTION_ID` set in `.env`
- [ ] `MEM0_API_KEY` set in `.env`
- [ ] Signature tests passing (run `test_email_signature.py`)
- [ ] Contact tests passing (run `test_auto_learn_contacts.py`)
- [ ] Review signature text (currently "Cheers, Ashley")
- [ ] Review newsletter detection threshold (currently 2 indicators)

---

## 🎉 You're Ready!

Both features are now active and will work automatically:

✅ **All outgoing emails** → Signed with "Cheers, Ashley"
✅ **All fetched emails** → Contacts learned, newsletters skipped

**No additional code changes needed** - just use `GmailSendEmail` and `AutoLearnContactFromEmail` as shown above!

---

**Total setup time**: ~5 minutes
**Complexity**: Low (mostly automatic)
**Maintenance**: Minimal (adjust thresholds as needed)

🚀 **Ready to deploy!**
