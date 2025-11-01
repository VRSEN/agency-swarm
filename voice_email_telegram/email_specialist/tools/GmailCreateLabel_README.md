# GmailCreateLabel Tool

## Overview
Create custom Gmail labels (folders/tags) for organizing emails using the Composio SDK.

## Purpose
Gmail labels are flexible organizational tools that allow users to:
- Categorize emails (e.g., "Clients", "Invoices", "Projects")
- Create hierarchical organization (e.g., "Work/ProjectA", "Work/ProjectB")
- Filter and search emails by label
- Auto-archive or show messages based on label settings

## Implementation Details

### Pattern
Based on validated pattern from `FINAL_VALIDATION_SUMMARY.md`:
- Uses Composio SDK `client.tools.execute()`
- Action: `GMAIL_CREATE_LABEL`
- Authentication: `user_id=entity_id` (NOT dangerously_skip_version_check)

### Code Structure
```python
from agency_swarm.tools import BaseTool
from composio import Composio

class GmailCreateLabel(BaseTool):
    name: str = Field(..., description="Label name")
    label_list_visibility: str = Field(default="labelShow")
    message_list_visibility: str = Field(default="show")
```

## Parameters

### Required
- **name** (str): Label name
  - Examples: "Clients", "Invoices", "Work/ProjectA"
  - Supports spaces: "Important Tasks"
  - Supports hierarchy: "Projects/2025/Q1"

### Optional
- **label_list_visibility** (str, default: "labelShow")
  - `"labelShow"`: Show label in Gmail sidebar
  - `"labelHide"`: Hide label from sidebar (still searchable)

- **message_list_visibility** (str, default: "show")
  - `"show"`: Show messages with this label in inbox
  - `"hide"`: Auto-archive messages (skip inbox)

## Return Value

### Success Response
```json
{
  "success": true,
  "label_id": "Label_123456789",
  "name": "Clients",
  "label_list_visibility": "labelShow",
  "message_list_visibility": "show",
  "type": "user",
  "message": "Successfully created label 'Clients'",
  "usage": {
    "add_to_messages": "Use GmailAddLabel with label_id='Label_123456789'",
    "search_emails": "Use GmailFetchEmails with query='label:Clients'",
    "list_all": "Use GmailListLabels to see all labels"
  }
}
```

### Error Response
```json
{
  "success": false,
  "error": "Label 'Clients' already exists. Use GmailListLabels to see existing labels.",
  "label_id": null,
  "name": "Clients",
  "suggestion": "Use GmailListLabels to find the existing label ID"
}
```

## Use Cases

### 1. Create Basic Label
```python
tool = GmailCreateLabel(name="Clients")
result = tool.run()
# Creates "Clients" label, visible in sidebar
```

### 2. Create Auto-Archive Label
```python
tool = GmailCreateLabel(
    name="Newsletters",
    label_list_visibility="labelShow",
    message_list_visibility="hide"
)
result = tool.run()
# Creates "Newsletters" label that auto-archives messages
```

### 3. Create Hierarchical Label
```python
tool = GmailCreateLabel(name="Work/ProjectA")
result = tool.run()
# Creates nested label under "Work" parent
```

### 4. Create Hidden Label
```python
tool = GmailCreateLabel(
    name="Archive",
    label_list_visibility="labelHide",
    message_list_visibility="hide"
)
result = tool.run()
# Creates hidden, auto-archiving label
```

## Voice Command Examples

User says to CEO:
- "Create a label for Clients"
  → CEO routes to GmailCreateLabel(name="Clients")

- "Add an Invoices label"
  → CEO routes to GmailCreateLabel(name="Invoices")

- "Make a label called Important Tasks"
  → CEO routes to GmailCreateLabel(name="Important Tasks")

- "Create a Work/ProjectA label"
  → CEO routes to GmailCreateLabel(name="Work/ProjectA")

## Integration with Other Tools

### After Creating Label
1. **Add label to messages**: Use `GmailAddLabel`
   ```python
   GmailAddLabel(message_id="msg_123", label_ids=["Label_123456789"])
   ```

2. **Search emails by label**: Use `GmailFetchEmails`
   ```python
   GmailFetchEmails(query="label:Clients")
   ```

3. **List all labels**: Use `GmailListLabels`
   ```python
   GmailListLabels()  # Shows new label in results
   ```

## Label Patterns

### Simple Labels
- "Clients"
- "Invoices"
- "Important"
- "To Review"

### Hierarchical Labels (nested)
- "Work/ProjectA"
- "Personal/Family"
- "Projects/2025/Q1"
- "Archive/Old/2023"

### Special Use Cases
- **Auto-Archive**: `message_list_visibility="hide"`
  - Good for: Newsletters, notifications, automated emails
  - Messages skip inbox but are still accessible

- **Hidden Labels**: `label_list_visibility="labelHide"`
  - Good for: Automated workflows, backend organization
  - Not visible in sidebar but still functional

## Validation

### Input Validation
- ✅ **Empty name**: Rejected with error
- ✅ **Invalid visibility**: Rejected with error
- ✅ **Whitespace names**: Trimmed automatically
- ✅ **Special characters**: Supported (except "/" which creates hierarchy)

### Error Handling
- ✅ **Missing credentials**: Clear error message
- ✅ **Duplicate label**: Suggests using GmailListLabels
- ✅ **API errors**: Returns detailed error information

## Testing

### Validation Tests (No API)
```bash
cd email_specialist/tools
python test_create_label_simple.py
```
Tests:
- Empty name validation
- Invalid visibility validation
- Tool structure validation
- Response structure validation

### Comprehensive Tests (Requires API)
```bash
cd email_specialist/tools
python test_gmail_create_label.py
```
Tests:
- Basic label creation
- Hidden label creation
- Hierarchical label creation
- Real-world use cases
- Error handling

## Requirements

### Environment Variables
```bash
COMPOSIO_API_KEY=your_api_key_here
GMAIL_ENTITY_ID=your_entity_id_here
```

### Dependencies
- `composio` - Composio SDK
- `agency_swarm` - Agency Swarm framework
- `pydantic` - Data validation
- `python-dotenv` - Environment variables

## System Labels vs Custom Labels

### System Labels (Cannot Create)
These already exist in Gmail:
- INBOX, SENT, DRAFT, TRASH, SPAM
- UNREAD, STARRED, IMPORTANT
- CATEGORY_PERSONAL, CATEGORY_SOCIAL, CATEGORY_PROMOTIONS

### Custom Labels (This Tool)
User-created organizational labels:
- Any name you choose
- Hierarchical organization supported
- Customizable visibility settings

## Limitations

1. **Gmail API Rate Limits**: Subject to Gmail API quotas
2. **Duplicate Names**: Cannot create label with existing name
3. **System Label Names**: Cannot use reserved names
4. **Name Length**: Gmail has max length limits (~256 chars)

## Related Tools

- **GmailListLabels**: List all existing labels (system + custom)
- **GmailAddLabel**: Add label to specific messages
- **GmailRemoveLabel**: Remove label from messages
- **GmailPatchLabel**: Edit label properties
- **GmailFetchEmails**: Search emails by label

## Status
✅ **READY FOR PRODUCTION**
- All validation tests passing
- Error handling complete
- Pattern validated against FINAL_VALIDATION_SUMMARY.md
- Response structure consistent with other Gmail tools

---

**Created**: November 1, 2025
**Pattern**: Composio SDK with `user_id=entity_id`
**Action**: GMAIL_CREATE_LABEL
**Coverage**: Phase 3 (Batch & Contacts) - Tool #16 of 24
