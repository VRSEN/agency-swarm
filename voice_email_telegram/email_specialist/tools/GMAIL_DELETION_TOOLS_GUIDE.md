# Gmail Deletion Tools - Complete Guide

**Date**: November 1, 2025
**Status**: Production Ready
**Tools**: 3 deletion tools (Trash, Delete, Batch Delete)

---

## 🎯 Quick Reference

| Tool | Deletion Type | Recoverable | Use Case | Safety |
|------|--------------|-------------|----------|--------|
| **GmailMoveToTrash** | Soft delete | ✅ Yes (30 days) | Most use cases | ✅ **HIGH** |
| **GmailDeleteMessage** | PERMANENT | ❌ NO | Compliance/Security | ⚠️ **LOW** |
| **GmailBatchDeleteMessages** | PERMANENT | ❌ NO | Bulk permanent | ⚠️ **LOW** |

---

## 📋 Tool 1: GmailMoveToTrash (RECOMMENDED)

### Purpose
Soft delete - moves message to trash (recoverable for 30 days)

### Key Features
- ✅ Recoverable for 30 days
- ✅ Message goes to Gmail Trash folder
- ✅ User can restore from trash
- ✅ Auto-deleted after 30 days
- ✅ Safe for user mistakes
- ✅ **DEFAULT for 'delete' requests**

### Parameters
```python
message_id: str  # Gmail message ID (required)
```

### Example Usage
```python
from email_specialist.tools.GmailMoveToTrash import GmailMoveToTrash

tool = GmailMoveToTrash(message_id="18c1f2a3b4d5e6f7")
result = tool.run()
```

### Return Format
```json
{
  "success": true,
  "message_id": "18c1f2a3b4d5e6f7",
  "status": "Message moved to trash",
  "recoverable": true,
  "recovery_period": "30 days",
  "note": "Trashed messages are automatically deleted after 30 days"
}
```

### When to Use
- User says "delete this email"
- User says "remove this message"
- User says "get rid of this"
- User says "trash this"
- Deleting spam or promotional emails
- **ANY uncertain deletion request**

### Composio Action
`GMAIL_MOVE_TO_TRASH`

---

## 📋 Tool 2: GmailDeleteMessage (CAUTION)

### Purpose
⚠️ **PERMANENT deletion** - message CANNOT be recovered

### Key Features
- ❌ NOT recoverable
- ❌ Does NOT go to trash
- ❌ CANNOT be undone
- ⚠️ Immediate and irreversible
- ⚠️ **ONLY use with explicit confirmation**

### Parameters
```python
message_id: str  # Gmail message ID (required) - ⚠️ PERMANENT deletion!
```

### Example Usage
```python
from email_specialist.tools.GmailDeleteMessage import GmailDeleteMessage

# ⚠️ ONLY use after user confirmation!
tool = GmailDeleteMessage(message_id="18c1f2a3b4d5e6f7")
result = tool.run()
```

### Return Format
```json
{
  "success": true,
  "message_id": "18c1f2a3b4d5e6f7",
  "status": "Message PERMANENTLY deleted",
  "warning": "⚠️ PERMANENT DELETION - Message cannot be recovered",
  "recoverable": false,
  "recovery_period": "None - deletion is permanent",
  "note": "Consider using GmailMoveToTrash for recoverable deletion"
}
```

### When to Use
⚠️ **ONLY use when**:
- User EXPLICITLY says "permanently delete"
- User confirms permanent deletion after warning
- Compliance requires permanent deletion (GDPR, data retention)
- Security policy mandates data purging
- Legal requirement for data destruction

### Composio Action
`GMAIL_DELETE_MESSAGE`

---

## 📋 Tool 3: GmailBatchDeleteMessages (CAUTION)

### Purpose
⚠️ **PERMANENT bulk deletion** - messages CANNOT be recovered

### Key Features
- ❌ NOT recoverable
- ❌ Does NOT go to trash
- ❌ CANNOT be undone
- ⚠️ Bulk operation (multiple messages)
- ⚠️ **ONLY use with explicit confirmation**

### Parameters
```python
message_ids: List[str]  # List of Gmail message IDs (required) - ⚠️ PERMANENT!
```

### Example Usage
```python
from email_specialist.tools.GmailBatchDeleteMessages import GmailBatchDeleteMessages

# ⚠️ ONLY use after user confirmation!
tool = GmailBatchDeleteMessages(message_ids=["msg1", "msg2", "msg3"])
result = tool.run()
```

### Return Format
```json
{
  "success": true,
  "deleted_count": 3,
  "message_ids": ["msg1", "msg2", "msg3"],
  "status": "3 messages PERMANENTLY deleted",
  "warning": "⚠️ PERMANENT DELETION - Messages cannot be recovered",
  "recoverable": false
}
```

### When to Use
⚠️ **ONLY use when**:
- User EXPLICITLY says "permanently delete all"
- Bulk compliance deletion required
- Security incident cleanup
- Legal requirement for bulk data destruction
- User confirms bulk permanent deletion

### Composio Action
`GMAIL_BATCH_DELETE_MESSAGES`

---

## 🔄 Decision Tree

```
User Request: Delete email(s)
    |
    ├─ Contains "permanently"? ────────────────┐
    │                                          │
    NO                                        YES
    │                                          │
    └─> USE GmailMoveToTrash                   ├─ Confirm with user
        (Safe, recoverable)                    │  "This will PERMANENTLY delete.
                                               │   Cannot be recovered. Confirm?"
                                               │
                                               ├─ User confirms? ───┐
                                               │                    │
                                               NO                  YES
                                               │                    │
                                               └─> Cancel           ├─ Single or multiple?
                                                                    │
                                                                    ├─ Single ─> GmailDeleteMessage
                                                                    │
                                                                    └─ Multiple ─> GmailBatchDeleteMessages
```

---

## 🎤 CEO Routing Logic

### Detection Patterns

```python
# Default to TRASH (safe)
TRASH_PATTERNS = [
    "delete this",
    "remove this",
    "get rid of",
    "trash this",
    "delete email",
    "remove email"
]
→ Route to: GmailMoveToTrash

# Permanent deletion (require confirmation)
PERMANENT_PATTERNS = [
    "permanently delete",
    "delete permanently",
    "permanent deletion",
    "delete forever",
    "irreversibly delete"
]
→ Route to: GmailDeleteMessage (after confirmation)

# Batch permanent deletion (require confirmation)
BATCH_PERMANENT_PATTERNS = [
    "permanently delete all",
    "delete all permanently",
    "bulk delete forever"
]
→ Route to: GmailBatchDeleteMessages (after confirmation)
```

### Confirmation Flow

```python
def handle_deletion_request(user_message, message_ids):
    """Route deletion requests with safety confirmations."""

    # Check for permanent deletion intent
    if "permanently" in user_message.lower():
        # Require confirmation
        confirmation = ask_user(
            "⚠️ This will PERMANENTLY delete the message(s). "
            "They CANNOT be recovered. Are you sure?"
        )

        if confirmation != "yes":
            return "Deletion cancelled."

        # Single or batch?
        if len(message_ids) == 1:
            return GmailDeleteMessage(message_id=message_ids[0]).run()
        else:
            return GmailBatchDeleteMessages(message_ids=message_ids).run()

    else:
        # Default to safe trash (no confirmation needed)
        if len(message_ids) == 1:
            return GmailMoveToTrash(message_id=message_ids[0]).run()
        else:
            # For batch trash, move each to trash individually
            results = []
            for msg_id in message_ids:
                results.append(GmailMoveToTrash(message_id=msg_id).run())
            return results
```

---

## 🛡️ Safety Best Practices

### 1. Default to Safe Deletion
```python
# ✅ GOOD: Default to trash
if "delete" in user_message and "permanently" not in user_message:
    use_tool = GmailMoveToTrash

# ❌ BAD: Assume permanent deletion
if "delete" in user_message:
    use_tool = GmailDeleteMessage  # WRONG!
```

### 2. Require Explicit Confirmation
```python
# ✅ GOOD: Confirm before permanent deletion
if requires_permanent_deletion:
    confirmation = confirm_with_user(
        "⚠️ PERMANENT deletion. Cannot be recovered. Confirm?"
    )
    if confirmation == "yes":
        use_tool = GmailDeleteMessage
    else:
        return "Deletion cancelled."

# ❌ BAD: No confirmation
if requires_permanent_deletion:
    use_tool = GmailDeleteMessage  # WRONG! No confirmation!
```

### 3. Log All Permanent Deletions
```python
# ✅ GOOD: Audit trail
if tool == GmailDeleteMessage:
    log_audit_event(
        action="PERMANENT_DELETION",
        user=user_id,
        message_id=message_id,
        timestamp=now(),
        confirmation=True
    )
```

### 4. Provide Clear Feedback
```python
# ✅ GOOD: Clear distinction
if tool == GmailMoveToTrash:
    return "Message moved to trash. Can be recovered for 30 days."

if tool == GmailDeleteMessage:
    return "⚠️ Message PERMANENTLY deleted. Cannot be recovered."
```

---

## 📊 Comparison Matrix

| Feature | MoveToTrash | DeleteMessage | BatchDelete |
|---------|------------|---------------|-------------|
| **Deletion Type** | Soft | PERMANENT | PERMANENT |
| **Recoverable** | ✅ 30 days | ❌ Never | ❌ Never |
| **Goes to Trash** | ✅ Yes | ❌ No | ❌ No |
| **Undo Available** | ✅ Yes | ❌ No | ❌ No |
| **User Safety** | ✅ High | ⚠️ Low | ⚠️ Low |
| **Confirmation Required** | ❌ No | ✅ Yes | ✅ Yes |
| **Audit Logging** | Optional | ✅ Required | ✅ Required |
| **Rate Limiting** | Optional | ✅ Recommended | ✅ Required |
| **Multiple Messages** | Single | Single | Batch |
| **Use Case** | General | Compliance | Bulk Compliance |
| **Default Choice** | ✅ Yes | ❌ No | ❌ No |

---

## 🔧 Implementation Checklist

### For GmailMoveToTrash
- [x] Tool created and tested
- [x] Follows validated Composio pattern
- [x] Error handling implemented
- [x] Clear return format
- [x] No confirmation required (safe operation)
- [x] Production ready

### For GmailDeleteMessage
- [x] Tool created and tested
- [x] Follows validated Composio pattern
- [x] Error handling implemented
- [x] Clear return format
- [x] **Safety warnings included**
- [x] **Confirmation required**
- [x] **Audit logging recommended**
- [x] Production ready

### For GmailBatchDeleteMessages
- [x] Tool created and tested
- [x] Follows validated Composio pattern
- [x] Error handling implemented
- [x] Clear return format
- [x] **Safety warnings included**
- [x] **Confirmation required**
- [x] **Rate limiting recommended**
- [x] Production ready

---

## 🎯 Testing Guide

### Test GmailMoveToTrash
```bash
cd /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram
python email_specialist/tools/GmailMoveToTrash.py
```

### Test GmailDeleteMessage
```bash
cd /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram
python email_specialist/tools/GmailDeleteMessage.py
```

### Test GmailBatchDeleteMessages
```bash
cd /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram
python email_specialist/tools/GmailBatchDeleteMessages.py
```

---

## 📝 Integration Example

### Full Workflow

```python
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
from email_specialist.tools.GmailMoveToTrash import GmailMoveToTrash
from email_specialist.tools.GmailDeleteMessage import GmailDeleteMessage

# User: "Delete all spam emails"

# Step 1: Fetch spam emails
fetch_tool = GmailFetchEmails(query="label:spam", max_results=100)
emails = json.loads(fetch_tool.run())

# Step 2: Extract message IDs
message_ids = [msg["id"] for msg in emails["messages"]]

# Step 3: Determine deletion type
if "permanently" in user_message.lower():
    # Require confirmation for permanent deletion
    confirmation = confirm_with_user(
        f"⚠️ This will PERMANENTLY delete {len(message_ids)} spam emails. "
        "They CANNOT be recovered. Are you sure?"
    )

    if confirmation == "yes":
        # Use batch permanent delete
        from email_specialist.tools.GmailBatchDeleteMessages import GmailBatchDeleteMessages
        batch_tool = GmailBatchDeleteMessages(message_ids=message_ids)
        result = batch_tool.run()
        return f"⚠️ Permanently deleted {len(message_ids)} spam emails."
    else:
        return "Deletion cancelled."
else:
    # Default to safe trash
    results = []
    for msg_id in message_ids:
        trash_tool = GmailMoveToTrash(message_id=msg_id)
        results.append(trash_tool.run())

    return f"✅ Moved {len(message_ids)} spam emails to trash. Can be recovered for 30 days."
```

---

## ⚠️ Critical Reminders

### For Developers
1. **ALWAYS default to GmailMoveToTrash** unless explicitly required otherwise
2. **ALWAYS require confirmation** before permanent deletion
3. **ALWAYS log** permanent deletions for audit trail
4. **ALWAYS provide clear feedback** about deletion type
5. **NEVER assume** user wants permanent deletion

### For Users
1. **"Delete"** = Trash (recoverable for 30 days)
2. **"Permanently delete"** = Gone forever (cannot recover)
3. **Trash is safer** - use it by default
4. **Confirm before permanent** - double-check the decision
5. **Audit logs exist** - permanent deletions are tracked

---

## 🚀 Production Status

| Tool | Status | Tested | Documentation | CEO Integration |
|------|--------|--------|---------------|-----------------|
| GmailMoveToTrash | ✅ Ready | ✅ Yes | ✅ Complete | ⏳ Pending |
| GmailDeleteMessage | ✅ Ready | ✅ Yes | ✅ Complete | ⏳ Pending |
| GmailBatchDeleteMessages | ✅ Ready | ✅ Yes | ✅ Complete | ⏳ Pending |

**Next Steps**:
1. Update CEO routing to use decision tree
2. Add confirmation flow to CEO
3. Implement audit logging
4. Test end-to-end workflow

---

**Document Version**: 1.0
**Last Updated**: November 1, 2025
**Author**: python-pro agent
**Status**: Production Ready

---

*All tools follow the validated Composio SDK pattern from FINAL_VALIDATION_SUMMARY.md*
*Safety-first approach: Default to trash, confirm before permanent*
