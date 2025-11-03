# Email Signature and Auto-Learning Contact System

Complete implementation guide for automatic email signatures and intelligent contact learning.

## Overview

Two major enhancements to the email system:

1. **Automatic Email Signature**: All outgoing emails automatically append "Cheers, Ashley"
2. **Auto-Learning Contacts**: Automatically extract and store contacts from received emails, filtering out newsletters

---

## Feature 1: Automatic Email Signature

### What It Does

- Automatically appends "Cheers, Ashley" to all outgoing emails
- Prevents signature duplication if already present
- Optional skip for automated/system emails

### Implementation

**Modified File**: `email_specialist/tools/GmailSendEmail.py`

**Key Features**:
- Automatic signature append before sending
- Duplicate detection (won't add if "Cheers, Ashley" already exists)
- Trailing whitespace cleanup
- Optional `skip_signature` parameter for special cases

### Usage

#### Basic Usage (Automatic Signature)

```python
from email_specialist.tools.GmailSendEmail import GmailSendEmail

# Signature automatically added
tool = GmailSendEmail(
    to="john@example.com",
    subject="Project Update",
    body="Hi John,\n\nHere's the latest update on the project."
)

result = tool.run()
# Email sent with signature:
# "Hi John,
#
# Here's the latest update on the project.
#
# Cheers, Ashley"
```

#### Skip Signature for Automated Emails

```python
# No signature for automated emails
tool = GmailSendEmail(
    to="system@example.com",
    subject="Automated Report",
    body="Daily report attached.",
    skip_signature=True
)

result = tool.run()
# Email sent without signature
```

#### Signature Already Present

```python
# Won't duplicate signature
tool = GmailSendEmail(
    to="sarah@example.com",
    subject="Quick Note",
    body="Hi Sarah,\n\nThanks for your help.\n\nCheers, Ashley"
)

result = tool.run()
# Signature not duplicated (already present)
```

### Response Format

```json
{
  "success": true,
  "message_id": "abc123",
  "thread_id": "xyz789",
  "to": "john@example.com",
  "subject": "Project Update",
  "signature_added": true,
  "sent_via": "composio",
  "message": "Email sent successfully via Composio Gmail integration"
}
```

---

## Feature 2: Auto-Learning Contact System

### What It Does

- Automatically extracts contacts from received emails
- Stores contact information in Mem0 for future reference
- **Intelligent Newsletter Detection**: Filters out newsletters and promotional emails
- Multi-indicator algorithm prevents false positives

### Implementation

**New File**: `memory_manager/tools/AutoLearnContactFromEmail.py`

### Newsletter Detection Algorithm

**Requires 2+ indicators** for newsletter classification:

#### Indicator 1: Email Headers
- `List-Unsubscribe`: Presence of unsubscribe header
- `List-Id`: Mailing list identifier
- `Precedence: bulk`: Bulk email marker

#### Indicator 2: From Address Patterns
- `noreply@`, `no-reply@`, `donotreply@`
- `newsletter@`, `marketing@`, `news@`
- `notifications@`, `updates@`

#### Indicator 3: Body Keywords
- "unsubscribe"
- "manage your preferences"
- "manage preferences"
- "opt out"
- "stop receiving"

### Usage

#### Basic Usage (Automatic Learning)

```python
from memory_manager.tools.AutoLearnContactFromEmail import AutoLearnContactFromEmail
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails

# Step 1: Fetch emails
fetch_tool = GmailFetchEmails(query="is:unread", max_results=10)
result = json.loads(fetch_tool.run())

# Step 2: Auto-learn contacts from each email
for email in result["messages"]:
    learn_tool = AutoLearnContactFromEmail(
        email_data=email,
        user_id="ashley_user_123"
    )

    learn_result = learn_tool.run()
    print(learn_result)
```

#### Force Add Newsletter Contact

```python
# Override newsletter detection
learn_tool = AutoLearnContactFromEmail(
    email_data=email,
    user_id="ashley_user_123",
    force_add=True  # Add even if newsletter detected
)

result = learn_tool.run()
```

### Response Formats

#### Success (Contact Learned)

```json
{
  "success": true,
  "skipped": false,
  "contact": {
    "name": "John Doe",
    "email": "john.doe@acmecorp.com",
    "subject": "Project Update",
    "date": "Mon, 1 Nov 2025 10:00:00 -0400"
  },
  "memory_id": "mem_abc123def456",
  "user_id": "ashley_user_123",
  "is_newsletter": false,
  "force_added": false,
  "message": "Successfully learned contact: John Doe <john.doe@acmecorp.com>"
}
```

#### Newsletter Skipped

```json
{
  "success": true,
  "skipped": true,
  "reason": "newsletter_detected",
  "email": "newsletter@marketing.com",
  "name": "Marketing Team",
  "indicators": [
    "Header: List-Unsubscribe",
    "From pattern: newsletter@"
  ],
  "message": "Skipped newsletter/promotional email from newsletter@marketing.com"
}
```

#### Error (Missing From Header)

```json
{
  "success": false,
  "error": "No From header found in email",
  "skipped": true
}
```

---

## Mem0 Storage Format

Contacts stored in Mem0 with comprehensive metadata:

```json
{
  "text": "Contact: John Doe, email: john.doe@acmecorp.com",
  "user_id": "ashley_user_123",
  "metadata": {
    "type": "contact",
    "name": "John Doe",
    "email": "john.doe@acmecorp.com",
    "source": "email_auto_learn",
    "learned_at": "2025-11-01T10:30:00.000Z",
    "subject": "Project Update",
    "date": "Mon, 1 Nov 2025 10:00:00 -0400",
    "force_added": false
  }
}
```

### Querying Learned Contacts

```python
from memory_manager.tools.Mem0Search import Mem0Search

# Search for specific contact
search_tool = Mem0Search(
    query="john.doe@acmecorp.com",
    user_id="ashley_user_123"
)

result = search_tool.run()
# Returns contact information from Mem0
```

---

## Integration Workflow

### Complete Email Processing Workflow

```python
import json
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
from email_specialist.tools.GmailSendEmail import GmailSendEmail
from memory_manager.tools.AutoLearnContactFromEmail import AutoLearnContactFromEmail

# 1. Fetch new emails
print("Fetching emails...")
fetch_tool = GmailFetchEmails(query="is:unread", max_results=20)
fetch_result = json.loads(fetch_tool.run())

if fetch_result["success"]:
    emails = fetch_result["messages"]
    print(f"Found {len(emails)} emails")

    # 2. Auto-learn contacts from each email
    print("\nLearning contacts...")
    for email in emails:
        learn_tool = AutoLearnContactFromEmail(
            email_data=email,
            user_id="ashley_user_123"
        )

        learn_result = json.loads(learn_tool.run())

        if learn_result.get("skipped"):
            print(f"  ⊘ Skipped: {learn_result.get('email', 'unknown')}")
            print(f"    Reason: {learn_result.get('reason', 'N/A')}")
        elif learn_result.get("success"):
            contact = learn_result.get("contact", {})
            print(f"  ✓ Learned: {contact.get('name')} <{contact.get('email')}>")

# 3. Send reply with automatic signature
print("\nSending reply...")
send_tool = GmailSendEmail(
    to="john.doe@acmecorp.com",
    subject="Re: Project Update",
    body="Hi John,\n\nThanks for the update. Everything looks good."
    # Signature automatically added
)

send_result = json.loads(send_tool.run())
if send_result["success"]:
    print("✓ Email sent with signature")
```

---

## Testing

### Test Email Signature

```bash
cd /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram
python tests/test_email_signature.py
```

**Tests**:
- ✓ Basic signature append
- ✓ Signature already present (no duplication)
- ✓ Empty body handling
- ✓ Trailing whitespace cleanup
- ✓ Skip signature option

### Test Auto-Learning Contacts

```bash
cd /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram
python tests/test_auto_learn_contacts.py
```

**Tests**:
- ✓ Newsletter detection (multi-indicator)
- ✓ Contact extraction (various formats)
- ✓ Full workflow with Mem0 storage
- ✓ Force add override
- ✓ Error handling

---

## Configuration

### Environment Variables

```bash
# Required for email sending
COMPOSIO_API_KEY=your_composio_api_key
GMAIL_CONNECTION_ID=your_gmail_connection_id

# Required for contact storage
MEM0_API_KEY=your_mem0_api_key
```

### Signature Customization

To change the signature, modify `GmailSendEmail.py`:

```python
def _append_signature(self, body: str) -> str:
    # Change signature here
    signature = "Best regards,\nYour Name"

    if signature in body:
        return body

    cleaned_body = body.rstrip()
    return f"{cleaned_body}\n\n{signature}"
```

### Newsletter Detection Tuning

To adjust newsletter detection sensitivity, modify `AutoLearnContactFromEmail.py`:

```python
def _is_newsletter(self, email_data: dict) -> tuple[bool, list[str]]:
    # ...

    # Change threshold (currently requires 2+ indicators)
    is_newsletter = len(indicators) >= 2  # Adjust this number

    return is_newsletter, indicator_details
```

---

## Deliverables Checklist

✅ **Modified Files**:
- `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/email_specialist/tools/GmailSendEmail.py`

✅ **New Files**:
- `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/memory_manager/tools/AutoLearnContactFromEmail.py`
- `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/tests/test_email_signature.py`
- `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/tests/test_auto_learn_contacts.py`
- `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/EMAIL_SIGNATURE_AND_CONTACTS_GUIDE.md` (this file)

✅ **Features Implemented**:
1. Automatic "Cheers, Ashley" signature on all outgoing emails
2. Signature duplicate detection
3. Optional skip signature for automated emails
4. Auto-learn contacts from received emails
5. Multi-indicator newsletter detection
6. Mem0 storage with comprehensive metadata
7. Force-add override for special cases

✅ **Testing**:
- Comprehensive test suite for signature functionality
- Comprehensive test suite for contact learning
- Unit tests for newsletter detection algorithm
- Integration workflow examples

---

## Troubleshooting

### Signature Not Appearing

**Problem**: Signature not added to sent emails

**Solutions**:
1. Check `skip_signature` parameter (should be `False` or omitted)
2. Verify signature not already in body text
3. Check GmailSendEmail tool logs for errors

### Contacts Not Being Learned

**Problem**: Contacts not stored in Mem0

**Solutions**:
1. Verify `MEM0_API_KEY` set in `.env`
2. Check if email classified as newsletter (see `indicators` in response)
3. Use `force_add=True` to override newsletter detection
4. Verify email has valid From header

### False Newsletter Detection

**Problem**: Regular emails being classified as newsletters

**Solutions**:
1. Check newsletter detection indicators in response
2. Adjust detection threshold in `_is_newsletter()` method
3. Use `force_add=True` for specific emails
4. Review sender patterns and body keywords

### Newsletter Not Being Filtered

**Problem**: Newsletter contacts being stored

**Solutions**:
1. Verify newsletter has at least 2 detection indicators
2. Add additional sender patterns or body keywords
3. Lower threshold in `_is_newsletter()` method
4. Check email headers for newsletter markers

---

## Future Enhancements

### Potential Improvements

1. **Configurable Signatures**
   - Store signature in Mem0 per user
   - Support HTML signatures
   - Multiple signature templates

2. **Advanced Contact Learning**
   - Deduplicate contacts (same email, different names)
   - Contact relationship tracking
   - Automatic contact categorization

3. **Smart Newsletter Handling**
   - ML-based newsletter detection
   - Newsletter importance scoring
   - Selective newsletter contact storage

4. **Contact Enrichment**
   - Extract phone numbers from signatures
   - Company/organization detection
   - Social media profile linking

---

## API Reference

### GmailSendEmail

```python
class GmailSendEmail(BaseTool):
    """
    Sends email with automatic signature append.
    """

    to: str                    # Required: Recipient email
    subject: str               # Required: Email subject
    body: str                  # Required: Email body
    cc: str = ""              # Optional: CC recipients
    bcc: str = ""             # Optional: BCC recipients
    skip_signature: bool = False  # Optional: Skip signature
```

### AutoLearnContactFromEmail

```python
class AutoLearnContactFromEmail(BaseTool):
    """
    Learns contacts from emails with newsletter filtering.
    """

    email_data: dict          # Required: Email from GmailFetchEmails
    user_id: str = "default_user"  # Optional: User ID for Mem0
    force_add: bool = False   # Optional: Override newsletter detection
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] Set `COMPOSIO_API_KEY` in production environment
- [ ] Set `GMAIL_CONNECTION_ID` in production environment
- [ ] Set `MEM0_API_KEY` in production environment
- [ ] Run signature tests: `python tests/test_email_signature.py`
- [ ] Run contact learning tests: `python tests/test_auto_learn_contacts.py`
- [ ] Verify signature appears in test emails
- [ ] Verify contacts stored correctly in Mem0
- [ ] Test newsletter detection with real newsletters
- [ ] Configure signature text if customization needed
- [ ] Adjust newsletter detection threshold if needed

### Monitoring

**Key Metrics to Monitor**:
1. Emails sent with signature vs. without
2. Contacts learned vs. newsletters skipped
3. Newsletter detection accuracy (false positives/negatives)
4. Mem0 storage success rate
5. Duplicate signature instances (should be 0)

---

## Support

For issues or questions:

1. Check test outputs: `tests/test_*.py`
2. Review error messages in tool responses (JSON format)
3. Verify environment variables set correctly
4. Check Composio and Mem0 API status
5. Review newsletter detection indicators in responses

---

**Implementation Complete** ✅

All features tested and ready for production deployment.
