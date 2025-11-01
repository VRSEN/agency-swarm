# GmailModifyThreadLabels - Quick Reference

**One-line summary**: Modify labels for entire Gmail threads (conversations) - ALL messages at once.

---

## 🔑 Key Difference

| Tool | Scope | Example |
|------|-------|---------|
| GmailAddLabel | 1 message | "Label this email" |
| **GmailModifyThreadLabels** | **All messages** | **"Label this conversation"** |

---

## ⚡ Quick Usage

```python
from tools.GmailModifyThreadLabels import GmailModifyThreadLabels

# Archive entire conversation
tool = GmailModifyThreadLabels(
    thread_id="18c2f3a1b4e5d6f7",
    remove_label_ids=["INBOX"]
)
tool.run()

# Star whole thread
tool = GmailModifyThreadLabels(
    thread_id="18c2f3a1b4e5d6f7",
    add_label_ids=["STARRED"]
)
tool.run()

# Organize project thread
tool = GmailModifyThreadLabels(
    thread_id="18c2f3a1b4e5d6f7",
    add_label_ids=["Label_ProjectX", "IMPORTANT"],
    remove_label_ids=["INBOX", "UNREAD"]
)
tool.run()
```

---

## 📋 Parameters

```python
thread_id: str           # Required - Gmail thread ID
add_label_ids: list      # Optional - Labels to ADD
remove_label_ids: list   # Optional - Labels to REMOVE
# Note: Must specify at least one operation (add OR remove)
```

---

## 🎯 Common Operations

| Operation | Code |
|-----------|------|
| Archive | `remove_label_ids=["INBOX"]` |
| Unarchive | `add_label_ids=["INBOX"]` |
| Star | `add_label_ids=["STARRED"]` |
| Unstar | `remove_label_ids=["STARRED"]` |
| Mark important | `add_label_ids=["IMPORTANT"]` |
| Mark read | `remove_label_ids=["UNREAD"]` |
| Move to trash | `add_label_ids=["TRASH"], remove_label_ids=["INBOX"]` |

---

## 🏷️ Label IDs

### System Labels (UPPERCASE)
`INBOX`, `UNREAD`, `STARRED`, `IMPORTANT`, `SENT`, `DRAFT`, `SPAM`, `TRASH`

### Category Labels
`CATEGORY_PERSONAL`, `CATEGORY_SOCIAL`, `CATEGORY_PROMOTIONS`, `CATEGORY_UPDATES`

### Custom Labels
`Label_ProjectX`, `Label_Q4`, `Label_Archive2024`
- Get IDs: Use `GmailListLabels` tool
- Create new: Use `GmailCreateLabel` tool

---

## ✅ Success Response

```json
{
  "success": true,
  "thread_id": "18c2f3a1b4e5d6f7",
  "modified_message_count": 5,
  "operations": [...],
  "message": "Successfully added 2 label(s) and removed 1 label(s) to/from thread"
}
```

---

## ❌ Common Errors

```json
{"error": "thread_id is required"}
{"error": "Must specify at least one of: add_label_ids or remove_label_ids"}
{"error": "Missing Composio credentials"}
```

---

## 🗣️ Voice Commands

User says:
- "Archive this entire conversation"
- "Star the whole thread from John"
- "Mark this discussion as important"
- "Label this conversation as ProjectX"

---

## 🧪 Test

```bash
# Unit tests (no API)
python email_specialist/tools/test_gmail_modify_thread_labels_unit.py

# Integration tests (requires API)
python email_specialist/tools/test_gmail_modify_thread_labels.py
```

---

## 🔗 Related Tools

- `GmailListThreads` - Find thread IDs
- `GmailFetchMessageByThreadId` - View thread details
- `GmailAddLabel` - Label single message
- `GmailListLabels` - List all labels

---

## ⚠️ Important Notes

1. **Thread vs Message**: This affects ALL messages in thread
2. **At least one operation**: Must specify add OR remove (or both)
3. **Label IDs**: Case-sensitive, system labels UPPERCASE
4. **Thread ID required**: Get from GmailListThreads

---

## 📁 Files

- `/email_specialist/tools/GmailModifyThreadLabels.py` - Tool
- `test_gmail_modify_thread_labels_unit.py` - Unit tests
- `test_gmail_modify_thread_labels.py` - Integration tests
- `GMAIL_MODIFY_THREAD_LABELS_GUIDE.md` - Full guide
- `GMAIL_MODIFY_THREAD_LABELS_SUMMARY.md` - Summary

---

**Status**: ✅ Production Ready | **Tests**: 20/20 Passed | **Pattern**: Validated Composio SDK
