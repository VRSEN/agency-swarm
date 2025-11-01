# GmailSendDraft Integration Guide

**Tool**: GmailSendDraft
**Action**: GMAIL_SEND_DRAFT
**Purpose**: Send existing Gmail drafts
**Status**: ✅ Production Ready

---

## 🎯 Overview

This guide provides complete integration instructions for the `GmailSendDraft` tool in production systems, focusing on voice-activated workflows, agent coordination, and enterprise patterns.

---

## 🏗️ Architecture Integration

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Voice Email System                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  User Voice Input                                           │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────────┐                                       │
│  │ Voice Specialist │ ◄─── "Send that draft"                │
│  └────────┬─────────┘                                       │
│           │                                                  │
│           ▼                                                  │
│  ┌──────────────────┐      ┌─────────────────┐            │
│  │ Email Specialist │ ───► │ GmailSendDraft  │            │
│  └────────┬─────────┘      └────────┬────────┘            │
│           │                          │                      │
│           │                          ▼                      │
│           │                  ┌──────────────┐              │
│           │                  │ Composio SDK │              │
│           │                  └──────┬───────┘              │
│           │                         │                      │
│           ▼                         ▼                      │
│  ┌─────────────────────────────────────────┐              │
│  │           Gmail API                      │              │
│  │  • Sends draft                           │              │
│  │  • Moves to SENT                         │              │
│  │  • Returns message_id                    │              │
│  └─────────────────────────────────────────┘              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Component Interactions

```python
# email_specialist/email_specialist.py

from agency_swarm import Agent
from .tools.GmailSendDraft import GmailSendDraft
from .tools.GmailListDrafts import GmailListDrafts
from .tools.GmailGetDraft import GmailGetDraft

class EmailSpecialist(Agent):
    def __init__(self):
        super().__init__(
            name="Email Specialist",
            description="Manages Gmail operations including draft sending",
            instructions="./instructions.md",
            tools=[
                GmailSendDraft,
                GmailListDrafts,
                GmailGetDraft,
                # ... other tools
            ]
        )
```

---

## 🎤 Voice Integration Patterns

### Pattern 1: Direct Send Command

**Voice Input**: *"Send that draft"*

```python
def handle_send_draft_command():
    """Handle voice command to send most recent draft"""

    # Step 1: List drafts to find most recent
    list_tool = GmailListDrafts(max_results=1)
    list_result = json.loads(list_tool.run())

    if not list_result.get("success") or not list_result.get("drafts"):
        return "No drafts found to send"

    # Step 2: Get draft ID
    draft_id = list_result["drafts"][0]["id"]
    draft_subject = list_result["drafts"][0].get("subject", "Untitled")

    # Step 3: Send draft
    send_tool = GmailSendDraft(draft_id=draft_id)
    send_result = json.loads(send_tool.run())

    # Step 4: Voice response
    if send_result.get("success"):
        return f"I've sent your draft email: {draft_subject}"
    else:
        return f"I couldn't send the draft. {send_result.get('error')}"
```

### Pattern 2: Review Before Send

**Voice Input**: *"Send the email to John"*

```python
def handle_send_to_recipient(recipient_name: str):
    """Find and send draft to specific recipient"""

    # Step 1: List all drafts
    list_tool = GmailListDrafts(max_results=50)
    drafts = json.loads(list_tool.run())

    # Step 2: Find drafts to recipient
    matching_drafts = [
        d for d in drafts.get("drafts", [])
        if recipient_name.lower() in d.get("to", "").lower()
    ]

    if not matching_drafts:
        return f"No drafts found for {recipient_name}"

    # Step 3: Get most recent match
    draft_id = matching_drafts[0]["id"]

    # Step 4: Review draft with user
    get_tool = GmailGetDraft(draft_id=draft_id)
    draft = json.loads(get_tool.run())

    # Voice review
    review_message = f"I found a draft to {draft['to']} with subject '{draft['subject']}'. Shall I send it?"

    # (User confirms via voice)
    user_confirmed = True  # From voice recognition

    if user_confirmed:
        # Step 5: Send draft
        send_tool = GmailSendDraft(draft_id=draft_id)
        result = json.loads(send_tool.run())

        if result.get("success"):
            return f"Email sent to {recipient_name}"
        else:
            return f"Failed to send: {result.get('error')}"
    else:
        return "Send cancelled"
```

### Pattern 3: Batch Send Confirmation

**Voice Input**: *"Send all pending drafts"*

```python
def handle_send_all_drafts():
    """Send all drafts with confirmation"""

    # Step 1: List all drafts
    list_tool = GmailListDrafts(max_results=100)
    drafts = json.loads(list_tool.run())

    draft_count = len(drafts.get("drafts", []))

    if draft_count == 0:
        return "No drafts to send"

    # Step 2: Voice confirmation
    confirm_message = f"You have {draft_count} drafts. Send all?"
    # (Get user confirmation)

    user_confirmed = True  # From voice recognition

    if user_confirmed:
        # Step 3: Send all drafts
        sent_count = 0
        failed_count = 0

        for draft in drafts["drafts"]:
            send_tool = GmailSendDraft(draft_id=draft["id"])
            result = json.loads(send_tool.run())

            if result.get("success"):
                sent_count += 1
            else:
                failed_count += 1

            # Rate limiting
            time.sleep(1)

        return f"Sent {sent_count} drafts. {failed_count} failed."
    else:
        return "Batch send cancelled"
```

---

## 🤖 Agent Coordination

### Multi-Agent Workflow

```python
# agency.py - Agency orchestration

from agency_swarm import Agency
from email_specialist.email_specialist import EmailSpecialist
from voice_specialist.voice_specialist import VoiceSpecialist
from ceo.ceo import CEO

# Define agency structure
agency = Agency([
    ceo,
    [ceo, email_specialist],
    [ceo, voice_specialist],
    [voice_specialist, email_specialist]
])

# Voice → Email specialist communication
"""
Voice Specialist receives: "Send that draft"
  ↓
Voice Specialist → Email Specialist: "send_draft_command"
  ↓
Email Specialist executes: GmailSendDraft
  ↓
Email Specialist → Voice Specialist: "Draft sent successfully"
  ↓
Voice Specialist responds to user: "I've sent your draft email"
"""
```

### Email Specialist Instructions

```markdown
# email_specialist/instructions.md

You are the Email Specialist responsible for Gmail operations.

## Draft Sending Protocol

When asked to send a draft:

1. **List Drafts**: Use GmailListDrafts to find available drafts
2. **Identify Target**: Match user intent to specific draft
3. **Review**: Use GmailGetDraft to verify draft content
4. **Confirm**: Ensure user approval before sending
5. **Send**: Use GmailSendDraft to send the draft
6. **Verify**: Confirm successful send with message_id
7. **Report**: Return clear status to requesting agent

## Error Handling

- If draft not found, report clearly
- If send fails, provide error details
- Never send without confirmation
- Always return structured results
```

### CEO Coordination

```python
# ceo/tools/WorkflowCoordinator.py

def coordinate_draft_send(draft_identifier: str):
    """
    CEO coordinates draft sending workflow
    """

    workflow = {
        "step_1": {
            "agent": "email_specialist",
            "tool": "GmailListDrafts",
            "instruction": f"Find draft matching: {draft_identifier}"
        },
        "step_2": {
            "agent": "email_specialist",
            "tool": "GmailGetDraft",
            "instruction": "Review draft content for approval"
        },
        "step_3": {
            "agent": "email_specialist",
            "tool": "GmailSendDraft",
            "instruction": "Send approved draft and confirm delivery"
        },
        "step_4": {
            "agent": "voice_specialist",
            "tool": "SpeakResponse",
            "instruction": "Confirm to user that draft was sent"
        }
    }

    return workflow
```

---

## 🔄 Complete Integration Example

### Full Voice-to-Send Pipeline

```python
# integration/voice_draft_sender.py

import json
from email_specialist.tools.GmailListDrafts import GmailListDrafts
from email_specialist.tools.GmailGetDraft import GmailGetDraft
from email_specialist.tools.GmailSendDraft import GmailSendDraft
from voice_specialist.tools.SpeakResponse import SpeakResponse

class VoiceDraftSender:
    """
    Complete integration: Voice command → Draft sent → Voice confirmation
    """

    def __init__(self):
        self.sent_history = []

    def process_voice_command(self, transcription: str) -> str:
        """
        Main entry point for voice commands
        """

        # Parse intent
        intent = self._parse_intent(transcription)

        if intent["action"] == "send_draft":
            return self._handle_send_draft(intent)
        elif intent["action"] == "send_to":
            return self._handle_send_to(intent["recipient"])
        else:
            return "I didn't understand that command"

    def _parse_intent(self, transcription: str) -> dict:
        """Parse voice command into intent"""

        transcription_lower = transcription.lower()

        if "send draft" in transcription_lower or "send that draft" in transcription_lower:
            return {"action": "send_draft"}

        if "send email to" in transcription_lower or "send to" in transcription_lower:
            # Extract recipient name
            # Simplified: "send email to John" → "John"
            words = transcription.split()
            to_index = words.index("to") if "to" in words else -1
            recipient = words[to_index + 1] if to_index >= 0 else None

            return {
                "action": "send_to",
                "recipient": recipient
            }

        return {"action": "unknown"}

    def _handle_send_draft(self, intent: dict) -> str:
        """Handle 'send draft' command"""

        # Step 1: List drafts
        list_tool = GmailListDrafts(max_results=1)
        list_result = json.loads(list_tool.run())

        if not list_result.get("success") or not list_result.get("drafts"):
            return self._speak("You don't have any drafts to send")

        # Step 2: Get draft details
        draft_id = list_result["drafts"][0]["id"]
        get_tool = GmailGetDraft(draft_id=draft_id)
        draft = json.loads(get_tool.run())

        if not draft.get("success"):
            return self._speak("I couldn't retrieve the draft details")

        # Step 3: Review with user (voice)
        subject = draft.get("subject", "Untitled")
        to = draft.get("to", "Unknown")
        review_msg = f"I found a draft to {to} with subject {subject}. Should I send it?"

        # Voice confirmation
        self._speak(review_msg)
        # (In real implementation, wait for voice confirmation)
        user_confirmed = True  # Simulated

        if not user_confirmed:
            return self._speak("Okay, I won't send the draft")

        # Step 4: Send draft
        send_tool = GmailSendDraft(draft_id=draft_id)
        send_result = json.loads(send_tool.run())

        # Step 5: Voice response
        if send_result.get("success"):
            message_id = send_result["message_id"]

            # Record in history
            self.sent_history.append({
                "draft_id": draft_id,
                "message_id": message_id,
                "subject": subject,
                "to": to,
                "sent_at": datetime.now().isoformat()
            })

            return self._speak(f"I've sent your email to {to}")
        else:
            error = send_result.get("error", "Unknown error")
            return self._speak(f"I couldn't send the email. {error}")

    def _handle_send_to(self, recipient: str) -> str:
        """Handle 'send email to [recipient]' command"""

        # Step 1: List all drafts
        list_tool = GmailListDrafts(max_results=50)
        drafts = json.loads(list_tool.run())

        # Step 2: Find matching draft
        matching = [
            d for d in drafts.get("drafts", [])
            if recipient.lower() in d.get("to", "").lower()
        ]

        if not matching:
            return self._speak(f"I couldn't find any drafts for {recipient}")

        # Step 3: Send first match
        draft_id = matching[0]["id"]
        send_tool = GmailSendDraft(draft_id=draft_id)
        result = json.loads(send_tool.run())

        if result.get("success"):
            return self._speak(f"Email sent to {recipient}")
        else:
            return self._speak(f"Failed to send email: {result.get('error')}")

    def _speak(self, message: str) -> str:
        """Convert text to speech"""
        speak_tool = SpeakResponse(text=message)
        speak_tool.run()
        return message

# Usage in agency
voice_sender = VoiceDraftSender()

# Voice input: "Send that draft"
response = voice_sender.process_voice_command("Send that draft")
# Output (voice): "I found a draft to john@example.com with subject Project Update. Should I send it?"
# User confirms: "Yes"
# Output (voice): "I've sent your email to john@example.com"
```

---

## 📊 Monitoring & Logging

### Production Logging

```python
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('GmailSendDraft')

def send_draft_with_logging(draft_id: str):
    """Send draft with comprehensive logging"""

    logger.info(f"Starting draft send: draft_id={draft_id}")

    try:
        # Send draft
        send_tool = GmailSendDraft(draft_id=draft_id)
        result = json.loads(send_tool.run())

        if result.get("success"):
            logger.info(f"Draft sent successfully: draft_id={draft_id}, message_id={result['message_id']}")

            # Log to database
            log_to_database({
                "event": "draft_sent",
                "draft_id": draft_id,
                "message_id": result["message_id"],
                "thread_id": result["thread_id"],
                "timestamp": datetime.now().isoformat()
            })

            return result
        else:
            logger.error(f"Draft send failed: draft_id={draft_id}, error={result.get('error')}")

            # Log failure
            log_to_database({
                "event": "draft_send_failed",
                "draft_id": draft_id,
                "error": result.get("error"),
                "timestamp": datetime.now().isoformat()
            })

            return result

    except Exception as e:
        logger.exception(f"Exception sending draft: draft_id={draft_id}")

        # Log exception
        log_to_database({
            "event": "draft_send_exception",
            "draft_id": draft_id,
            "exception": str(e),
            "timestamp": datetime.now().isoformat()
        })

        raise
```

### Metrics Collection

```python
from prometheus_client import Counter, Histogram

# Define metrics
drafts_sent_total = Counter('drafts_sent_total', 'Total drafts sent')
drafts_failed_total = Counter('drafts_failed_total', 'Total draft send failures')
draft_send_duration = Histogram('draft_send_duration_seconds', 'Time to send draft')

def send_draft_with_metrics(draft_id: str):
    """Send draft with metrics collection"""

    with draft_send_duration.time():
        send_tool = GmailSendDraft(draft_id=draft_id)
        result = json.loads(send_tool.run())

        if result.get("success"):
            drafts_sent_total.inc()
        else:
            drafts_failed_total.inc()

        return result
```

---

## 🔒 Security & Compliance

### Authorization Checks

```python
def send_draft_with_authorization(draft_id: str, user_id: str):
    """Send draft with user authorization check"""

    # Step 1: Verify user owns the draft
    get_tool = GmailGetDraft(draft_id=draft_id)
    draft = json.loads(get_tool.run())

    if not draft.get("success"):
        return {"error": "Draft not found or access denied"}

    # Step 2: Check user permissions
    if not user_can_send_email(user_id):
        logger.warning(f"Unauthorized send attempt: user_id={user_id}, draft_id={draft_id}")
        return {"error": "User not authorized to send emails"}

    # Step 3: Compliance checks
    compliance_result = check_email_compliance(draft)
    if not compliance_result["compliant"]:
        return {"error": f"Compliance violation: {compliance_result['reason']}"}

    # Step 4: Send draft
    send_tool = GmailSendDraft(draft_id=draft_id)
    return json.loads(send_tool.run())
```

### Audit Trail

```python
def send_draft_with_audit(draft_id: str, user_id: str):
    """Send draft with full audit trail"""

    audit_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "action": "send_draft",
        "draft_id": draft_id,
        "ip_address": get_client_ip(),
        "user_agent": get_user_agent()
    }

    try:
        # Send draft
        send_tool = GmailSendDraft(draft_id=draft_id)
        result = json.loads(send_tool.run())

        # Complete audit entry
        audit_entry["status"] = "success" if result.get("success") else "failed"
        audit_entry["message_id"] = result.get("message_id")
        audit_entry["error"] = result.get("error")

        # Store audit entry
        store_audit_log(audit_entry)

        return result

    except Exception as e:
        audit_entry["status"] = "exception"
        audit_entry["exception"] = str(e)
        store_audit_log(audit_entry)
        raise
```

---

## 🧪 Testing Integration

### Integration Test Example

```python
import unittest
from unittest.mock import Mock, patch

class TestGmailSendDraftIntegration(unittest.TestCase):
    """Integration tests for GmailSendDraft in production system"""

    def setUp(self):
        """Set up test environment"""
        self.draft_id = "test_draft_123"

    @patch('composio.Composio')
    def test_voice_to_send_integration(self, mock_composio):
        """Test complete voice → send workflow"""

        # Mock Composio response
        mock_composio.return_value.tools.execute.return_value = {
            "successful": True,
            "data": {
                "id": "msg_sent_123",
                "threadId": "thread_123"
            }
        }

        # Simulate voice command
        voice_input = "Send that draft"

        # Process command
        sender = VoiceDraftSender()
        response = sender.process_voice_command(voice_input)

        # Verify
        self.assertIn("sent", response.lower())

    def test_error_handling_integration(self):
        """Test error handling across integration"""

        # Simulate invalid draft
        send_tool = GmailSendDraft(draft_id="invalid_draft")
        result = json.loads(send_tool.run())

        # Verify graceful failure
        self.assertFalse(result.get("success"))
        self.assertIn("error", result)

if __name__ == '__main__':
    unittest.main()
```

---

## 📈 Performance Optimization

### Caching Draft Metadata

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_draft(draft_id: str):
    """Cache draft metadata to reduce API calls"""

    get_tool = GmailGetDraft(draft_id=draft_id)
    return get_tool.run()

def send_draft_optimized(draft_id: str):
    """Send draft with cached metadata"""

    # Use cached draft data for validation
    draft = json.loads(get_cached_draft(draft_id))

    if draft.get("success"):
        # Send without additional API call
        send_tool = GmailSendDraft(draft_id=draft_id)
        return send_tool.run()
```

### Batch Processing

```python
import asyncio

async def send_drafts_batch(draft_ids: list):
    """Send multiple drafts concurrently"""

    async def send_single(draft_id):
        send_tool = GmailSendDraft(draft_id=draft_id)
        return json.loads(send_tool.run())

    # Send all drafts concurrently
    results = await asyncio.gather(*[send_single(d) for d in draft_ids])

    return results

# Usage
draft_ids = ["draft_1", "draft_2", "draft_3"]
results = asyncio.run(send_drafts_batch(draft_ids))
```

---

## ✅ Deployment Checklist

### Pre-Production

- [ ] Environment variables configured (`COMPOSIO_API_KEY`, `GMAIL_ENTITY_ID`)
- [ ] Composio Gmail integration connected
- [ ] `GMAIL_SEND_DRAFT` action enabled
- [ ] Test suite passing (`python test_gmail_send_draft.py`)
- [ ] Integration tests passing
- [ ] Error handling tested
- [ ] Logging configured
- [ ] Metrics collection set up
- [ ] Security checks implemented
- [ ] Audit trail configured

### Production

- [ ] Monitor error rates
- [ ] Track success/failure metrics
- [ ] Set up alerts for failures
- [ ] Review audit logs regularly
- [ ] Monitor API rate limits
- [ ] User feedback collection
- [ ] Performance monitoring
- [ ] Compliance verification

---

## 🎓 Best Practices Summary

1. **Always review before send** - Use `GmailGetDraft` to verify content
2. **Handle errors gracefully** - Never fail silently
3. **Log everything** - Comprehensive audit trail
4. **Validate permissions** - Ensure user authorization
5. **Rate limit batch operations** - Respect Gmail API limits
6. **Cache when possible** - Reduce API calls
7. **Monitor metrics** - Track success/failure rates
8. **Test thoroughly** - Integration and unit tests

---

**Status**: ✅ Production Ready
**Last Updated**: 2025-11-01
**Version**: 1.0.0
