# GmailDeleteDraft Quick Reference

## 🚀 30-Second Quick Start

```python
from email_specialist.tools import GmailDeleteDraft

# Delete a draft
tool = GmailDeleteDraft(draft_id="r-1234567890123456789")
result = tool.run()
# Returns: {"success": true, "deleted": true, ...}
```

---

## ⚠️ CRITICAL Safety Info

- ❌ **PERMANENT DELETION** - Cannot be undone
- ✅ Deletes **DRAFTS ONLY** (not sent emails)
- 💡 Use `GmailGetDraft` to verify before deleting
- 🔒 Use `GmailMoveToTrash` for sent emails

---

## 📋 Parameters

| Parameter | Required | Default | Example |
|-----------|----------|---------|---------|
| `draft_id` | ✅ Yes | - | `"r-1234567890123456789"` |
| `user_id` | ❌ No | `"me"` | `"me"` |

---

## 📖 Common Use Cases

### 1. Voice Rejection Flow
```python
# User says "No, delete it"
tool = GmailDeleteDraft(draft_id=current_draft_id)
result = tool.run()
```

### 2. Cleanup Old Drafts
```python
# Delete multiple drafts
for draft_id in old_draft_ids:
    tool = GmailDeleteDraft(draft_id=draft_id)
    result = tool.run()
```

### 3. Cancel After Review
```python
# User reviews and cancels
tool = GmailDeleteDraft(draft_id=draft_from_review)
result = tool.run()
```

---

## ✅ Success Response

```json
{
  "success": true,
  "draft_id": "r-1234567890123456789",
  "deleted": true,
  "message": "Draft deleted successfully (PERMANENT)",
  "warning": "Deletion is permanent and cannot be undone"
}
```

---

## ❌ Error Response

```json
{
  "success": false,
  "draft_id": "r-xxx",
  "deleted": false,
  "error": "Draft not found",
  "possible_reasons": [
    "Draft ID does not exist",
    "Draft was already deleted",
    "Insufficient permissions"
  ]
}
```

---

## 🔄 Integration Patterns

### Voice Workflow
```python
Create Draft → Review → User Rejects → DELETE ✓
```

### Agent Integration
```python
from agency_swarm.tools import BaseTool
from email_specialist.tools import GmailDeleteDraft

# Add to agent tools
tools = [GmailDeleteDraft, ...]
```

### Error Handling
```python
result = tool.run()
data = json.loads(result)

if data["success"]:
    print(f"✓ Deleted: {data['draft_id']}")
else:
    print(f"✗ Error: {data['error']}")
```

---

## 🔗 Related Tools

| Tool | Use When |
|------|----------|
| `GmailListDrafts` | Get draft IDs to delete |
| `GmailGetDraft` | Verify draft before deleting |
| `GmailCreateDraft` | Create drafts |
| `GmailSendDraft` | Alternative to deletion |

---

## 🐛 Quick Troubleshooting

**"Missing credentials"**
```bash
# Add to .env:
COMPOSIO_API_KEY=your_key
GMAIL_ENTITY_ID=your_entity_id
```

**"Draft not found"**
```python
# Verify draft exists first:
verify = GmailGetDraft(draft_id=draft_id)
```

**"Empty draft_id"**
```python
# Must provide valid draft_id:
tool = GmailDeleteDraft(draft_id="r-xxx")  # ✓
tool = GmailDeleteDraft(draft_id="")       # ✗
```

---

## 📚 Full Documentation

- **Complete Guide:** [GMAIL_DELETE_DRAFT_README.md](./GMAIL_DELETE_DRAFT_README.md)
- **Integration Guide:** [GMAIL_DELETE_DRAFT_INTEGRATION.md](./GMAIL_DELETE_DRAFT_INTEGRATION.md)
- **Test Suite:** [test_gmail_delete_draft.py](./test_gmail_delete_draft.py)

---

## ⚙️ Production Checklist

- ✅ Set `COMPOSIO_API_KEY` in `.env`
- ✅ Set `GMAIL_ENTITY_ID` in `.env`
- ✅ Enable `GMAIL_DELETE_DRAFT` in Composio dashboard
- ✅ Test with `python test_gmail_delete_draft.py`
- ✅ Always verify draft_id before deletion
- ✅ Implement error handling in production code

---

**Status:** Production Ready ✅
**Version:** 1.0.0
**Last Updated:** 2024-11-01
