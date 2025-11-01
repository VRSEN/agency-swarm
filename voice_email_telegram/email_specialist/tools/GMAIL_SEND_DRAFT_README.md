# GmailSendDraft Tool

**Purpose**: Send existing Gmail draft emails (convert draft to sent email)
**Action**: `GMAIL_SEND_DRAFT`
**Status**: ✅ Production Ready
**Pattern**: Validated Composio SDK Pattern

---

## 📋 Overview

The `GmailSendDraft` tool sends an existing Gmail draft email in one action. This is the final step in the draft workflow, converting a reviewed draft into a sent email.

### Key Features

- ✅ **Send existing drafts** - Convert draft to sent email instantly
- ✅ **Voice workflow ready** - "Send that draft" command support
- ✅ **Approval workflows** - Review before send patterns
- ✅ **Comprehensive error handling** - Validates draft_id, credentials, API responses
- ✅ **Full response data** - Returns message_id, thread_id, labels, and metadata

---

## 🚀 Quick Start

### Basic Usage

```python
from GmailSendDraft import GmailSendDraft

# Send a draft
tool = GmailSendDraft(draft_id="draft_abc123xyz")
result = tool.run()
print(result)
```

### Expected Response

```json
{
  "success": true,
  "message_id": "msg_18f5a1b2c3d4e5f6",
  "thread_id": "thread_18f5a1b2c3d4e5f6",
  "draft_id": "draft_abc123xyz",
  "message": "Draft draft_abc123xyz sent successfully as message msg_18f5a1b2c3d4e5f6",
  "sent_via": "composio_sdk",
  "label_ids": ["SENT", "INBOX"],
  "raw_data": { ... }
}
```

---

## 📖 Use Cases

### 1. Voice-Activated Send

**Scenario**: User says "Send that draft"

```python
# Step 1: List drafts to find most recent
from GmailListDrafts import GmailListDrafts
list_tool = GmailListDrafts(max_results=1)
drafts = json.loads(list_tool.run())

# Step 2: Send the draft
if drafts.get("success") and drafts.get("drafts"):
    draft_id = drafts["drafts"][0]["id"]
    send_tool = GmailSendDraft(draft_id=draft_id)
    result = send_tool.run()

    # Step 3: Voice confirmation
    result_obj = json.loads(result)
    if result_obj.get("success"):
        print(f"✓ Draft sent successfully!")
```

### 2. Review and Approve Workflow

**Scenario**: User reviews draft, then approves sending

```python
from GmailCreateDraft import GmailCreateDraft
from GmailGetDraft import GmailGetDraft
from GmailSendDraft import GmailSendDraft

# Step 1: Create draft
create_tool = GmailCreateDraft(
    to="client@example.com",
    subject="Project Update",
    body="Here's the latest status..."
)
draft_result = json.loads(create_tool.run())
draft_id = draft_result["draft_id"]

# Step 2: Review draft
review_tool = GmailGetDraft(draft_id=draft_id)
draft_content = json.loads(review_tool.run())
print(f"Review: {draft_content['snippet']}")

# Step 3: User approves → Send
user_approved = True  # User confirmation
if user_approved:
    send_tool = GmailSendDraft(draft_id=draft_id)
    result = json.loads(send_tool.run())
    print(f"Sent: {result['message_id']}")
```

### 3. Batch Send Approved Drafts

**Scenario**: Send multiple reviewed drafts

```python
approved_draft_ids = [
    "draft_report_1",
    "draft_report_2",
    "draft_report_3"
]

sent_messages = []
for draft_id in approved_draft_ids:
    tool = GmailSendDraft(draft_id=draft_id)
    result = json.loads(tool.run())

    if result.get("success"):
        sent_messages.append(result["message_id"])
        print(f"✓ Sent: {draft_id} → {result['message_id']}")
    else:
        print(f"✗ Failed: {draft_id} - {result['error']}")

print(f"\nSent {len(sent_messages)} drafts")
```

### 4. Scheduled Send Pattern

**Scenario**: Create drafts now, send later

```python
import time
from datetime import datetime, timedelta

# Create drafts with scheduled send times
drafts_to_send = [
    {"draft_id": "draft_morning", "send_at": "09:00"},
    {"draft_id": "draft_afternoon", "send_at": "14:00"},
]

for draft_config in drafts_to_send:
    draft_id = draft_config["draft_id"]
    send_time = draft_config["send_at"]

    # Wait until send time (simplified example)
    print(f"Scheduled: {draft_id} at {send_time}")

    # At scheduled time:
    tool = GmailSendDraft(draft_id=draft_id)
    result = json.loads(tool.run())
    print(f"Sent at {datetime.now()}: {result['message_id']}")
```

### 5. AI Agent Approval Flow

**Scenario**: AI creates draft, human approves, AI sends

```python
# AI creates draft
ai_draft = GmailCreateDraft(
    to="team@company.com",
    subject="Weekly Summary - AI Generated",
    body="[AI-generated content]"
)
draft_result = json.loads(ai_draft.run())
draft_id = draft_result["draft_id"]

# Human reviews and approves
print(f"Review draft {draft_id} in Gmail...")
approval = input("Approve send? (yes/no): ")

# AI sends if approved
if approval.lower() == "yes":
    send_tool = GmailSendDraft(draft_id=draft_id)
    result = json.loads(send_tool.run())
    print(f"AI sent email: {result['message_id']}")
else:
    print("Send cancelled. Draft remains in drafts.")
```

---

## 🔧 Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `draft_id` | str | **Yes** | - | Gmail draft ID to send |
| `user_id` | str | No | `"me"` | Gmail user ID (authenticated user) |

### Getting Draft IDs

Use these tools to get draft IDs:

```python
# Option 1: From GmailCreateDraft
create_tool = GmailCreateDraft(...)
result = json.loads(create_tool.run())
draft_id = result["draft_id"]

# Option 2: From GmailListDrafts
list_tool = GmailListDrafts(max_results=10)
result = json.loads(list_tool.run())
draft_ids = [d["id"] for d in result["drafts"]]

# Option 3: From GmailGetDraft (if you have the ID)
get_tool = GmailGetDraft(draft_id="known_draft_id")
result = json.loads(get_tool.run())
```

---

## 📤 Response Format

### Success Response

```json
{
  "success": true,
  "message_id": "msg_18f5a1b2c3d4e5f6",
  "thread_id": "thread_18f5a1b2c3d4e5f6",
  "draft_id": "draft_abc123xyz",
  "message": "Draft draft_abc123xyz sent successfully as message msg_18f5a1b2c3d4e5f6",
  "sent_via": "composio_sdk",
  "label_ids": ["SENT", "INBOX"],
  "raw_data": {
    "id": "msg_18f5a1b2c3d4e5f6",
    "threadId": "thread_18f5a1b2c3d4e5f6",
    "labelIds": ["SENT"]
  }
}
```

### Error Response

```json
{
  "success": false,
  "error": "Draft not found: draft_invalid",
  "message_id": null,
  "draft_id": "draft_invalid",
  "message": "Failed to send draft draft_invalid",
  "raw_response": { ... }
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | Whether send was successful |
| `message_id` | str | Sent message ID (null on failure) |
| `thread_id` | str | Gmail thread ID |
| `draft_id` | str | Original draft ID |
| `message` | str | Human-readable status message |
| `sent_via` | str | Always "composio_sdk" |
| `label_ids` | list | Gmail labels applied to message |
| `raw_data` | dict | Full API response data |

---

## ⚠️ Error Handling

### Common Errors

#### 1. Missing Credentials

```json
{
  "success": false,
  "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env",
  "message_id": null,
  "draft_id": "draft_123"
}
```

**Solution**: Configure `.env` file:
```bash
COMPOSIO_API_KEY=your_api_key_here
GMAIL_ENTITY_ID=your_entity_id_here
```

#### 2. Empty Draft ID

```json
{
  "success": false,
  "error": "draft_id is required and cannot be empty",
  "message_id": null,
  "draft_id": null
}
```

**Solution**: Provide valid draft_id:
```python
tool = GmailSendDraft(draft_id="draft_abc123")  # Valid ID
```

#### 3. Draft Not Found

```json
{
  "success": false,
  "error": "Draft not found or already sent",
  "message_id": null,
  "draft_id": "draft_nonexistent"
}
```

**Solution**: Verify draft exists using `GmailListDrafts` or `GmailGetDraft`

#### 4. Draft Already Sent

Once a draft is sent, it's removed from drafts. Attempting to send again will fail.

**Solution**: Check if draft still exists before sending:
```python
# Verify draft exists
get_tool = GmailGetDraft(draft_id=draft_id)
check = json.loads(get_tool.run())

if check.get("success"):
    # Draft exists, safe to send
    send_tool = GmailSendDraft(draft_id=draft_id)
    result = send_tool.run()
else:
    print("Draft no longer exists (may have been sent)")
```

---

## 🔄 Complete Draft Workflow

### End-to-End Example

```python
from GmailCreateDraft import GmailCreateDraft
from GmailGetDraft import GmailGetDraft
from GmailSendDraft import GmailSendDraft
from GmailGetMessage import GmailGetMessage
import json

# STEP 1: Create Draft
print("1. Creating draft...")
create_tool = GmailCreateDraft(
    to="recipient@example.com",
    subject="Important Update",
    body="This is an important message."
)
create_result = json.loads(create_tool.run())

if not create_result.get("success"):
    print(f"Failed to create draft: {create_result.get('error')}")
    exit()

draft_id = create_result["draft_id"]
print(f"✓ Draft created: {draft_id}")

# STEP 2: Review Draft
print("\n2. Reviewing draft...")
review_tool = GmailGetDraft(draft_id=draft_id)
review_result = json.loads(review_tool.run())

if review_result.get("success"):
    print(f"Subject: {review_result['subject']}")
    print(f"To: {review_result['to']}")
    print(f"Preview: {review_result['snippet']}")
else:
    print(f"Failed to review: {review_result.get('error')}")
    exit()

# STEP 3: User Approval (simulated)
print("\n3. Awaiting approval...")
user_approved = True  # In real app, get user confirmation

# STEP 4: Send Draft
if user_approved:
    print("\n4. Sending draft...")
    send_tool = GmailSendDraft(draft_id=draft_id)
    send_result = json.loads(send_tool.run())

    if not send_result.get("success"):
        print(f"Failed to send: {send_result.get('error')}")
        exit()

    message_id = send_result["message_id"]
    print(f"✓ Draft sent: {message_id}")

    # STEP 5: Verify Sent
    print("\n5. Verifying sent message...")
    verify_tool = GmailGetMessage(message_id=message_id)
    verify_result = json.loads(verify_tool.run())

    if verify_result.get("success"):
        print(f"✓ Confirmed in SENT: {verify_result['snippet']}")
        print(f"Thread: {verify_result['thread_id']}")
    else:
        print(f"Verification failed: {verify_result.get('error')}")
else:
    print("\n4. Send cancelled by user")

print("\n✅ Workflow complete!")
```

---

## 🧪 Testing

### Run Test Suite

```bash
cd email_specialist/tools
python test_gmail_send_draft.py
```

### Test Coverage

The test suite includes:

1. ✅ **Send simple draft** - Basic functionality
2. ✅ **Send with user_id** - Parameter validation
3. ✅ **Empty draft_id** - Input validation
4. ✅ **Invalid draft_id** - Error handling
5. ✅ **Missing credentials** - Configuration validation
6. ✅ **Response structure** - Output format validation
7. ✅ **Voice workflow** - Complete integration test

### Manual Testing

```python
# Create a test draft
from GmailCreateDraft import GmailCreateDraft
create_tool = GmailCreateDraft(
    to="your-email@gmail.com",
    subject="[TEST] Send Draft Tool",
    body="This is a test draft for GmailSendDraft validation."
)
result = json.loads(create_tool.run())
draft_id = result["draft_id"]

# Send the test draft
from GmailSendDraft import GmailSendDraft
send_tool = GmailSendDraft(draft_id=draft_id)
send_result = send_tool.run()
print(send_result)

# Check your Gmail sent folder for the test email
```

---

## 🔒 Security & Best Practices

### 1. Validate Before Sending

Always review draft content before sending:

```python
# DON'T: Send without review
send_tool = GmailSendDraft(draft_id=draft_id)
result = send_tool.run()

# DO: Review then send
review_tool = GmailGetDraft(draft_id=draft_id)
review = json.loads(review_tool.run())

if review.get("success"):
    print(f"Sending to: {review['to']}")
    print(f"Subject: {review['subject']}")

    confirmation = input("Confirm send? (yes/no): ")
    if confirmation.lower() == "yes":
        send_tool = GmailSendDraft(draft_id=draft_id)
        result = send_tool.run()
```

### 2. Handle Errors Gracefully

```python
send_tool = GmailSendDraft(draft_id=draft_id)
result = json.loads(send_tool.run())

if result.get("success"):
    # Success path
    message_id = result["message_id"]
    log_sent_email(message_id, draft_id)
else:
    # Error path
    error_msg = result.get("error", "Unknown error")
    log_error(f"Failed to send draft {draft_id}: {error_msg}")
    notify_user(f"Email send failed: {error_msg}")
```

### 3. Prevent Double-Sending

```python
sent_drafts = set()  # Track sent drafts

def safe_send_draft(draft_id):
    if draft_id in sent_drafts:
        return {"error": "Draft already sent"}

    send_tool = GmailSendDraft(draft_id=draft_id)
    result = json.loads(send_tool.run())

    if result.get("success"):
        sent_drafts.add(draft_id)

    return result
```

### 4. Rate Limiting

Gmail has rate limits. For batch operations:

```python
import time

draft_ids = ["draft_1", "draft_2", "draft_3", ...]

for draft_id in draft_ids:
    send_tool = GmailSendDraft(draft_id=draft_id)
    result = send_tool.run()

    # Rate limit: 1 send per second
    time.sleep(1)
```

---

## 🔗 Integration Examples

### With Voice Assistant

```python
def handle_voice_command(command: str):
    """Process voice commands for email sending"""

    if "send draft" in command.lower():
        # Get most recent draft
        list_tool = GmailListDrafts(max_results=1)
        drafts = json.loads(list_tool.run())

        if drafts.get("drafts"):
            draft_id = drafts["drafts"][0]["id"]

            # Send draft
            send_tool = GmailSendDraft(draft_id=draft_id)
            result = json.loads(send_tool.run())

            if result.get("success"):
                return f"Draft sent successfully. Message ID {result['message_id']}"
            else:
                return f"Failed to send draft: {result.get('error')}"
        else:
            return "No drafts found to send"

    return "Command not recognized"
```

### With Workflow Automation

```python
def automated_newsletter_send():
    """Send pre-scheduled newsletter drafts"""

    # List drafts with specific subject pattern
    list_tool = GmailListDrafts(max_results=100)
    drafts = json.loads(list_tool.run())

    newsletter_drafts = [
        d for d in drafts.get("drafts", [])
        if "Newsletter" in d.get("subject", "")
    ]

    sent_count = 0
    for draft in newsletter_drafts:
        send_tool = GmailSendDraft(draft_id=draft["id"])
        result = json.loads(send_tool.run())

        if result.get("success"):
            sent_count += 1
            print(f"✓ Sent: {draft['subject']}")
        else:
            print(f"✗ Failed: {draft['subject']} - {result.get('error')}")

    return f"Sent {sent_count}/{len(newsletter_drafts)} newsletters"
```

---

## 📚 Related Tools

| Tool | Purpose | Relationship |
|------|---------|--------------|
| `GmailCreateDraft` | Create new drafts | Provides `draft_id` for sending |
| `GmailListDrafts` | List all drafts | Find drafts to send |
| `GmailGetDraft` | View draft details | Review before sending |
| `GmailSendEmail` | Send new email directly | Alternative to draft workflow |
| `GmailGetMessage` | View sent message | Verify sent draft |

---

## ✅ Production Checklist

Before deploying to production:

- [ ] Configure `COMPOSIO_API_KEY` in `.env`
- [ ] Configure `GMAIL_ENTITY_ID` in `.env`
- [ ] Connect Gmail integration in Composio dashboard
- [ ] Enable `GMAIL_SEND_DRAFT` action
- [ ] Run test suite: `python test_gmail_send_draft.py`
- [ ] Test with real draft in staging
- [ ] Implement error handling in application
- [ ] Add logging for sent drafts
- [ ] Configure rate limiting if batch sending
- [ ] Set up monitoring/alerts for failures

---

## 🐛 Troubleshooting

### Problem: "Missing Composio credentials"

**Cause**: Environment variables not set

**Solution**:
```bash
# Create .env file
echo "COMPOSIO_API_KEY=your_key" >> .env
echo "GMAIL_ENTITY_ID=your_entity" >> .env
```

### Problem: "Draft not found"

**Cause**: Draft ID invalid or draft already sent

**Solution**:
```python
# Verify draft exists
list_tool = GmailListDrafts()
drafts = json.loads(list_tool.run())
valid_draft_ids = [d["id"] for d in drafts.get("drafts", [])]

if draft_id in valid_draft_ids:
    # Safe to send
    send_tool = GmailSendDraft(draft_id=draft_id)
```

### Problem: Rate limit exceeded

**Cause**: Too many API calls

**Solution**:
```python
import time

# Add delay between sends
time.sleep(1)  # 1 second delay
```

---

## 📞 Support

- **Issues**: Check error messages in response JSON
- **Testing**: Run `python test_gmail_send_draft.py`
- **Documentation**: See `FINAL_VALIDATION_SUMMARY.md`
- **Pattern**: Based on validated Composio SDK pattern

---

**Status**: ✅ Production Ready
**Last Updated**: 2025-11-01
**Version**: 1.0.0
