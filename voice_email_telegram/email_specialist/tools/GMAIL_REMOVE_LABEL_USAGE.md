# GmailRemoveLabel - Quick Usage Guide

## 🎯 Purpose
PERMANENTLY delete a custom Gmail label (removes it from all emails and deletes the label itself).

## ⚠️ CRITICAL WARNING
- This **DELETES THE LABEL ITSELF**, not emails
- Action is **PERMANENT** and **CANNOT BE UNDONE**
- Label is removed from **ALL EMAILS** that have it
- Emails themselves are **NOT DELETED** (only the label tag is removed)

## 🛡️ Safety Features
- **System labels CANNOT be deleted** (INBOX, SENT, STARRED, IMPORTANT, etc.)
- Built-in validation prevents accidental deletions
- Clear error messages guide users

## 📝 Quick Start

### 1. Import the Tool
```python
from email_specialist.tools.GmailRemoveLabel import GmailRemoveLabel
```

### 2. Basic Usage
```python
# Delete a custom label
tool = GmailRemoveLabel(label_id="Label_OldProject")
result = tool.run()
```

### 3. Response Format
```json
{
  "success": true,
  "deleted_label_id": "Label_OldProject",
  "message": "Label 'Label_OldProject' has been permanently deleted",
  "warning": "This action is PERMANENT. The label has been removed from all emails."
}
```

## 🔄 Recommended Workflow

```python
# Step 1: List all labels first
from email_specialist.tools.GmailListLabels import GmailListLabels
list_tool = GmailListLabels()
labels = list_tool.run()

# Step 2: Identify the label to delete (must be custom/user type)
# Find label_id from the list (e.g., "Label_OldProject")

# Step 3: Confirm with user (recommended)
# "This will permanently delete the label. Continue?"

# Step 4: Delete the label
delete_tool = GmailRemoveLabel(label_id="Label_OldProject")
result = delete_tool.run()
```

## 🚫 What You CANNOT Delete
System labels are protected:
- INBOX, SENT, DRAFT, TRASH, SPAM
- IMPORTANT, STARRED, UNREAD
- CATEGORY_PERSONAL, CATEGORY_SOCIAL, CATEGORY_PROMOTIONS
- CATEGORY_UPDATES, CATEGORY_FORUMS

Attempting to delete these will return:
```json
{
  "success": false,
  "error": "Cannot delete system label 'INBOX'. Only custom labels can be deleted.",
  "safety_warning": "System labels (INBOX, SENT, STARRED, etc.) are protected"
}
```

## 💡 Use Cases

### 1. Clean Up Old Labels
```python
# User: "Delete the 'Old Project' label"
tool = GmailRemoveLabel(label_id="Label_OldProject")
result = tool.run()
```

### 2. Remove Unused Labels
```python
# User: "Clean up my unused labels"
unused_labels = ["Label_Temp", "Label_Test", "Label_Archived"]
for label_id in unused_labels:
    tool = GmailRemoveLabel(label_id=label_id)
    result = tool.run()
    print(result)
```

### 3. Delete Test Labels
```python
# After testing, clean up
tool = GmailRemoveLabel(label_id="Label_Testing123")
result = tool.run()
```

## 🔑 Parameters

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| label_id | str | Yes | Label ID to delete | "Label_123" |

**How to get label_id:**
Use `GmailListLabels` tool to see all labels and their IDs.

## 🎯 Related Tools

| Tool | Purpose | Difference |
|------|---------|------------|
| **GmailRemoveLabel** | Delete the label itself | PERMANENT - deletes label |
| **GmailBatchModifyMessages** | Remove label from specific messages | TEMPORARY - label still exists |
| **GmailListLabels** | List all labels | Get label_id for deletion |
| **GmailCreateLabel** | Create new labels | Opposite operation |
| **GmailAddLabel** | Add labels to messages | Opposite operation |

## ⚖️ Remove Label vs. Delete Label

**This tool (GmailRemoveLabel):**
- Deletes the LABEL ITSELF
- Permanent deletion
- Affects ALL emails with this label
- Label cannot be used again (unless recreated)

**GmailBatchModifyMessages (remove label from messages):**
- Removes label from SPECIFIC MESSAGES only
- Label still exists in Gmail
- Can be re-added to messages later
- Non-destructive operation

## 🔧 Production Requirements
- Set `COMPOSIO_API_KEY` in `.env`
- Set `GMAIL_ENTITY_ID` in `.env`
- Gmail account connected via Composio
- **Recommended**: User confirmation before deletion

## 📊 Error Handling

### Missing Credentials
```json
{
  "success": false,
  "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env"
}
```

### Empty label_id
```json
{
  "success": false,
  "error": "label_id is required"
}
```

### Label Not Found
```json
{
  "success": false,
  "error": "Label 'Label_XYZ' not found. Use GmailListLabels to see available labels."
}
```

### Permission Denied
```json
{
  "success": false,
  "error": "Permission denied. Cannot delete label 'INBOX'. It may be a system label."
}
```

## ✅ Best Practices

1. **Always list labels first** - Use GmailListLabels to see what exists
2. **Confirm with user** - "This will permanently delete [label]. Continue?"
3. **Verify it's custom** - Check that label type is "user" (not "system")
4. **Consider alternatives** - Maybe just remove from specific messages?
5. **Log deletions** - Track what was deleted for audit trail
6. **Handle errors** - Gracefully handle "not found" or "permission denied"

## 🚨 Common Mistakes

### ❌ Wrong: Trying to delete system labels
```python
tool = GmailRemoveLabel(label_id="INBOX")  # Will fail with safety warning
```

### ✅ Correct: Delete custom labels only
```python
tool = GmailRemoveLabel(label_id="Label_CustomProject")  # Works
```

### ❌ Wrong: Not listing labels first
```python
# How do you know the label_id?
tool = GmailRemoveLabel(label_id="???")
```

### ✅ Correct: List labels first
```python
# Step 1: List labels to find ID
list_tool = GmailListLabels()
labels = list_tool.run()

# Step 2: Use the correct label_id
tool = GmailRemoveLabel(label_id="Label_ABC123")
```

## 📈 Testing

Run the built-in tests:
```bash
python email_specialist/tools/GmailRemoveLabel.py
```

This will test:
- ✅ System label protection (INBOX, STARRED, IMPORTANT, etc.)
- ✅ Missing label_id validation
- ✅ Custom label deletion
- ✅ Error handling

---

**Ready for Production**: ✅ YES
**File**: `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/email_specialist/tools/GmailRemoveLabel.py`
**Documentation**: Complete
**Testing**: Validated

---

*For detailed implementation info, see GMAIL_REMOVE_LABEL_SUMMARY.md*
