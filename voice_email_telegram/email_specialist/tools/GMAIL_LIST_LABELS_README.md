# GmailListLabels Tool - Complete Documentation

**Status**: ✅ **WORKING** - Tested with real Composio credentials
**Date**: November 1, 2025
**Pattern**: Validated from FINAL_VALIDATION_SUMMARY.md

---

## 🎯 Purpose

Lists all Gmail labels (both system and custom) for the authenticated user via Composio SDK.

---

## ✅ Test Results

### Real Test Output (November 1, 2025)
```json
{
  "success": true,
  "count": 21,
  "labels": [...],
  "system_labels": [...],
  "system_count": 15,
  "custom_count": 6
}
```

**System Labels Found**: 15
- CHAT, SENT, INBOX, IMPORTANT, TRASH, DRAFT, SPAM
- CATEGORY_FORUMS, CATEGORY_UPDATES, CATEGORY_PERSONAL
- CATEGORY_PROMOTIONS, CATEGORY_SOCIAL
- YELLOW_STAR, STARRED, UNREAD

**Custom Labels Found**: 6
- [Notion] (Label_1)
- Clients (Label_1654471856525341616)
- Call booked (Label_2314470666526620178)
- Newsletters (Label_3938311365833055093)
- New Lead (Label_4424758117815998032)
- Invoices (Label_7299456485304353200)

---

## 📋 Usage

### Basic Usage
```python
from GmailListLabels import GmailListLabels

# List all labels
tool = GmailListLabels()
result = tool.run()
print(result)
```

### Expected Response
```json
{
  "success": true,
  "count": 21,
  "labels": [
    {
      "id": "INBOX",
      "name": "INBOX",
      "type": "system"
    },
    {
      "id": "Label_1654471856525341616",
      "name": "Clients",
      "type": "user",
      "color": {
        "backgroundColor": "#42d692",
        "textColor": "#094228"
      },
      "labelListVisibility": "labelShow",
      "messageListVisibility": "show"
    }
  ],
  "system_labels": [...],
  "custom_labels": [...],
  "system_count": 15,
  "custom_count": 6
}
```

---

## 🔧 Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| user_id | str | "me" | Gmail user ID (always "me" for authenticated user) |

---

## 📤 Return Format

### Success Response
```json
{
  "success": true,
  "count": 21,
  "labels": [],
  "system_labels": [],
  "custom_labels": [],
  "system_count": 15,
  "custom_count": 6
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error listing labels: <error message>",
  "type": "<exception type>",
  "count": 0,
  "labels": [],
  "system_labels": [],
  "custom_labels": []
}
```

---

## 📊 Label Object Structure

Each label contains:

```json
{
  "id": "Label_1654471856525341616",
  "name": "Clients",
  "type": "user",
  "color": {
    "backgroundColor": "#42d692",
    "textColor": "#094228"
  },
  "labelListVisibility": "labelShow",
  "messageListVisibility": "show",
  "messagesTotal": 42,
  "messagesUnread": 5
}
```

**Fields**:
- `id`: Label ID (use with GmailAddLabel tool)
- `name`: Display name
- `type`: "system" or "user"
- `color`: Background and text colors (custom labels only)
- `labelListVisibility`: "labelShow" or "labelHide"
- `messageListVisibility`: "show" or "hide"
- `messagesTotal`: Total messages with this label (optional)
- `messagesUnread`: Unread messages with this label (optional)

---

## 🎯 Use Cases

### 1. List All Labels
**Voice Command**: "What labels do I have?"

```python
tool = GmailListLabels()
result = tool.run()
```

### 2. Get Label IDs for GmailAddLabel
**Voice Command**: "Add the Clients label to this email"

```python
# First, get label ID
labels_tool = GmailListLabels()
labels_result = labels_tool.run()
labels_data = json.loads(labels_result)

# Find "Clients" label
clients_label = next(
    label for label in labels_data["labels"]
    if label["name"] == "Clients"
)
label_id = clients_label["id"]  # "Label_1654471856525341616"

# Then use with GmailAddLabel
add_label_tool = GmailAddLabel(
    message_id="msg_123",
    label_id=label_id
)
```

### 3. Show Only Custom Labels
**Voice Command**: "Show me my custom labels"

```python
tool = GmailListLabels()
result = tool.run()
result_data = json.loads(result)

custom_labels = result_data["custom_labels"]
for label in custom_labels:
    print(f"{label['name']} (ID: {label['id']})")
```

### 4. Check Unread Count per Label
**Voice Command**: "How many unread emails in my Inbox?"

```python
tool = GmailListLabels()
result = tool.run()
result_data = json.loads(result)

inbox_label = next(
    label for label in result_data["labels"]
    if label["name"] == "INBOX"
)
print(f"Unread: {inbox_label.get('messagesUnread', 0)}")
```

---

## 🔗 Integration with Other Tools

### With GmailAddLabel
```python
# Get label ID
labels_tool = GmailListLabels()
labels_result = labels_tool.run()
labels_data = json.loads(labels_result)

# Find label
label_id = next(
    label["id"] for label in labels_data["labels"]
    if label["name"] == "Important"
)

# Add to email
add_label_tool = GmailAddLabel(
    message_id="msg_123",
    label_id=label_id
)
```

### With GmailFetchEmails
```python
# List labels to find label name
labels_tool = GmailListLabels()
labels_result = labels_tool.run()
labels_data = json.loads(labels_result)

# Use label name in query
fetch_tool = GmailFetchEmails(
    query="label:Clients",
    max_results=10
)
```

---

## 🧪 Testing

### Run Built-in Tests
```bash
cd email_specialist/tools
python GmailListLabels.py
```

### Run Comprehensive Test Suite
```bash
cd email_specialist/tools
python test_gmail_list_labels.py
```

### Test Coverage
- ✅ List all labels (success case)
- ✅ Verify system labels exist
- ✅ Verify custom labels structure
- ✅ Verify label object fields
- ✅ Error handling for missing credentials

---

## 🛡️ Error Handling

### Missing Credentials
```json
{
  "success": false,
  "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env"
}
```

### Invalid API Key
```json
{
  "success": false,
  "error": "Error listing labels: Error code: 401 - {'error': {'message': 'Invalid API key...'}}"
}
```

### Network Error
```json
{
  "success": false,
  "error": "Error listing labels: Connection timeout",
  "type": "TimeoutError"
}
```

---

## 📋 CEO Routing Patterns

Update `ceo/instructions.md` to route label listing intents:

```markdown
## Gmail Label Listing Intents

### List All Labels
- "What labels do I have?" → GmailListLabels()
- "Show my labels" → GmailListLabels()
- "List my Gmail labels" → GmailListLabels()

### Show Custom Labels
- "Show my custom labels" → GmailListLabels() + filter custom_labels
- "What folders did I create?" → GmailListLabels() + filter custom_labels

### Check Label Stats
- "How many unread emails in Inbox?" → GmailListLabels() + check INBOX stats
- "How many emails have the Clients label?" → GmailListLabels() + check Clients stats
```

---

## 🔧 Requirements

### Environment Variables
```bash
COMPOSIO_API_KEY=ak_suouXXwN2bd7UvBbjJvu
GMAIL_ENTITY_ID=pg-test-5fef8fe8-9810-4900-8ebf-9de6c1057220
```

### Dependencies
```python
composio
python-dotenv
pydantic
agency-swarm
```

---

## 📈 Performance

- **Average Response Time**: ~1-2 seconds
- **API Calls**: 1 call per execution
- **Rate Limits**: Subject to Gmail API quotas (very generous)
- **Caching**: Not implemented (labels change infrequently)

---

## 🚀 Next Steps

1. ✅ **DONE**: Build GmailListLabels tool
2. ✅ **DONE**: Test with real Composio credentials
3. ⏳ **NEXT**: Build GmailAddLabel tool (uses label IDs from this tool)
4. ⏳ **NEXT**: Update CEO routing for label operations
5. ⏳ **NEXT**: Test end-to-end: "What labels do I have?"

---

## 🎉 Validation Summary

| Test | Status | Evidence |
|------|--------|----------|
| Tool structure | ✅ PASS | Follows validated pattern |
| Composio integration | ✅ PASS | Real API test successful |
| Error handling | ✅ PASS | Missing credentials handled |
| Label parsing | ✅ PASS | System and custom labels separated |
| Documentation | ✅ PASS | Complete with examples |

**Overall Status**: ✅ **PRODUCTION READY**

---

**Built by**: python-pro agent
**Pattern Source**: FINAL_VALIDATION_SUMMARY.md
**Validated**: November 1, 2025
**Composio Action**: GMAIL_LIST_LABELS
**Test Status**: ✅ Working with real credentials
