# GmailAddLabel Tool - Usage Guide

## Overview
The `GmailAddLabel` tool adds labels to Gmail messages. Labels in Gmail are similar to folders or tags in other email systems.

## Basic Usage

```python
from tools.GmailAddLabel import GmailAddLabel

# Add IMPORTANT label to a message
tool = GmailAddLabel(
    message_id="18c2f3a1b4e5d6f7",
    label_ids=["IMPORTANT"]
)
result = tool.run()
```

## Common Use Cases

### 1. Mark as Important
```python
tool = GmailAddLabel(
    message_id="msg_123",
    label_ids=["IMPORTANT"]
)
```

### 2. Star a Message
```python
tool = GmailAddLabel(
    message_id="msg_123",
    label_ids=["STARRED"]
)
```

### 3. Mark as Unread
```python
tool = GmailAddLabel(
    message_id="msg_123",
    label_ids=["UNREAD"]
)
```

### 4. Move to Inbox (Unarchive)
```python
tool = GmailAddLabel(
    message_id="msg_123",
    label_ids=["INBOX"]
)
```

### 5. Add Custom Label
```python
# First, get your custom label ID with GmailListLabels
tool = GmailAddLabel(
    message_id="msg_123",
    label_ids=["Label_ProjectX"]
)
```

### 6. Add Multiple Labels at Once
```python
tool = GmailAddLabel(
    message_id="msg_123",
    label_ids=["IMPORTANT", "STARRED", "Label_Work"]
)
```

## System Label IDs

### Commonly Used
- `IMPORTANT` - Mark as important
- `STARRED` - Star the message
- `UNREAD` - Mark as unread
- `INBOX` - Show in inbox
- `SENT` - Move to sent folder
- `DRAFT` - Mark as draft
- `SPAM` - Mark as spam
- `TRASH` - Move to trash

### Category Labels
- `CATEGORY_PERSONAL` - Personal category
- `CATEGORY_SOCIAL` - Social updates, media
- `CATEGORY_PROMOTIONS` - Deals, offers
- `CATEGORY_UPDATES` - Confirmations, receipts
- `CATEGORY_FORUMS` - Mailing lists, forums

## Custom Labels

Custom labels follow the format: `Label_<name>` or `Label_<id>`

To find your custom label IDs:
```python
from tools.GmailListLabels import GmailListLabels

list_tool = GmailListLabels()
labels = list_tool.run()
# Look for your custom label ID in the response
```

## Response Format

### Success Response
```json
{
  "success": true,
  "message_id": "18c2f3a1b4e5d6f7",
  "labels_added": ["IMPORTANT", "STARRED"],
  "current_labels": ["INBOX", "UNREAD", "IMPORTANT", "STARRED"],
  "thread_id": "18c2f3a1b4e5d6f7",
  "message": "Successfully added 2 label(s) to message"
}
```

### Error Response
```json
{
  "error": "message_id is required"
}
```

## Integration with CEO Agent

The CEO agent routes label operations automatically:

**User:** "Mark this email as important"
- CEO detects intent: organize/label
- CEO calls: `GmailAddLabel(message_id=<msg_id>, label_ids=["IMPORTANT"])`

**User:** "Star the email from John"
- CEO fetches message from John
- CEO calls: `GmailAddLabel(message_id=<msg_id>, label_ids=["STARRED"])`

**User:** "Label this as urgent and work-related"
- CEO calls: `GmailAddLabel(message_id=<msg_id>, label_ids=["IMPORTANT", "Label_Work"])`

## Related Tools

- **GmailListLabels** - List all available labels
- **GmailCreateLabel** - Create new custom labels
- **GmailRemoveLabel** - Remove labels from messages
- **GmailBatchModifyMessages** - Add/remove labels on multiple messages at once

## Notes

1. **Label IDs are case-sensitive** - Use `IMPORTANT` not `important`
2. **System labels use UPPERCASE** - `STARRED`, `INBOX`, `UNREAD`
3. **Custom labels use Label_ prefix** - Get exact ID with `GmailListLabels`
4. **For batch operations** - Use `GmailBatchModifyMessages` instead
5. **To remove labels** - Use `GmailRemoveLabel` tool

## Requirements

- Valid Composio API key (`COMPOSIO_API_KEY` in .env)
- Gmail entity ID (`GMAIL_ENTITY_ID` in .env)
- Gmail account connected via Composio
- Valid Gmail message ID

## Validation

The tool includes:
- ✅ Input validation (message_id required, label_ids required)
- ✅ Proper error handling
- ✅ Composio SDK integration pattern
- ✅ JSON response format
- ✅ Comprehensive documentation

## Testing

Run the test suite:
```bash
python email_specialist/tools/test_gmail_add_label.py
```

Run standalone tests:
```bash
python email_specialist/tools/GmailAddLabel.py
```
