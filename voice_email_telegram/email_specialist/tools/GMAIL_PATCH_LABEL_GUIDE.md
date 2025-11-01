# GmailPatchLabel Tool - Quick Reference Guide

## Overview
Edit properties of existing Gmail labels including name, visibility, and colors.

**Action**: `GMAIL_PATCH_LABEL`
**Status**: ✅ Production Ready
**Pattern**: Validated from FINAL_VALIDATION_SUMMARY.md

---

## Parameters

### Required
- **label_id** (str) - Label ID to edit (get from GmailListLabels)

### Optional (at least one required)
- **name** (str) - New label name
- **label_list_visibility** (str) - Show/hide in sidebar
  - `"labelShow"` - Show in sidebar
  - `"labelHide"` - Hide from sidebar
  - `"labelShowIfUnread"` - Show only if unread
- **message_list_visibility** (str) - Show/hide messages
  - `"show"` - Show messages
  - `"hide"` - Hide messages
- **background_color** (str) - Hex color for background (e.g., `"#ff0000"`)
- **text_color** (str) - Hex color for text (e.g., `"#ffffff"`)

---

## Quick Examples

### Rename Label
```python
GmailPatchLabel(
    label_id="Label_123",
    name="Project Alpha"
)
```

### Change Colors
```python
GmailPatchLabel(
    label_id="Label_123",
    background_color="#ff0000",  # Red
    text_color="#ffffff"         # White
)
```

### Update Visibility
```python
GmailPatchLabel(
    label_id="Label_123",
    label_list_visibility="labelHide"
)
```

### Update All Properties
```python
GmailPatchLabel(
    label_id="Label_456",
    name="Important Clients",
    label_list_visibility="labelShow",
    message_list_visibility="show",
    background_color="#4285f4",
    text_color="#ffffff"
)
```

---

## Common Color Themes

### Google Colors
```python
# Blue (Google Blue)
background_color="#4285f4", text_color="#ffffff"

# Red (Google Red)
background_color="#ea4335", text_color="#ffffff"

# Yellow (Google Yellow)
background_color="#fbbc04", text_color="#000000"

# Green (Google Green)
background_color="#34a853", text_color="#000000"
```

### Priority Colors
```python
# High Priority (Red)
background_color="#ff0000", text_color="#ffffff"

# Medium Priority (Orange)
background_color="#ff6d00", text_color="#ffffff"

# Low Priority (Green)
background_color="#34a853", text_color="#000000"
```

### Custom Themes
```python
# Purple
background_color="#9c27b0", text_color="#ffffff"

# Teal
background_color="#00bcd4", text_color="#000000"

# Pink
background_color="#e91e63", text_color="#ffffff"
```

---

## Voice Command Examples

### Rename Operations
- "Rename 'Project A' label to 'Project Alpha'"
- "Change label name from Clients to Important Clients"
- "Rename the Work label to Business"

### Color Operations
- "Change label color to red"
- "Make label blue"
- "Update label to green theme"
- "Set label to high priority color" (red)

### Visibility Operations
- "Hide label from sidebar"
- "Show label in sidebar"
- "Show label only if unread"
- "Hide messages with this label"

---

## Limitations

### Cannot Modify
❌ System labels (INBOX, SENT, TRASH, SPAM, DRAFT, UNREAD, STARRED, IMPORTANT)
❌ Label ID (permanent identifier)
❌ Category labels (CATEGORY_PERSONAL, CATEGORY_SOCIAL, etc.)

### Can Modify
✅ Custom label names
✅ Custom label visibility
✅ Custom label colors
✅ Any user-created labels (Label_*)

---

## Error Handling

### System Label Protection
```json
{
  "success": false,
  "error": "Cannot modify system label 'INBOX'. Only custom labels can be edited."
}
```

### Color Format Validation
```json
{
  "success": false,
  "error": "background_color must be in hex format (e.g., '#ff0000')"
}
```

### Visibility Validation
```json
{
  "success": false,
  "error": "Invalid label_list_visibility. Must be one of: labelShow, labelHide, labelShowIfUnread"
}
```

### No Properties Specified
```json
{
  "success": false,
  "error": "At least one property must be specified to update (name, visibility, or colors)"
}
```

---

## Response Format

### Success Response
```json
{
  "success": true,
  "label_id": "Label_123",
  "updated_properties": {
    "name": "Project Alpha",
    "background_color": "#ff0000",
    "text_color": "#ffffff"
  },
  "label": {
    "id": "Label_123",
    "name": "Project Alpha",
    "type": "user",
    "labelListVisibility": "labelShow",
    "messageListVisibility": "show",
    "color": {
      "backgroundColor": "#ff0000",
      "textColor": "#ffffff"
    },
    "messagesTotal": 42,
    "messagesUnread": 5
  },
  "message": "Successfully updated 3 property/properties for label"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error updating label: [error message]",
  "type": "ErrorType",
  "label_id": "Label_123"
}
```

---

## Integration with Other Tools

### Get Label ID First
```python
# 1. List labels to get ID
from GmailListLabels import GmailListLabels
labels = GmailListLabels().run()

# 2. Patch the label
from GmailPatchLabel import GmailPatchLabel
result = GmailPatchLabel(
    label_id="Label_123",
    name="New Name"
).run()
```

### Workflow Examples

#### Organize Project Labels
```python
# 1. Create label
GmailCreateLabel(name="Project X").run()

# 2. Get label ID
labels = GmailListLabels().run()
label_id = # extract from labels

# 3. Update colors
GmailPatchLabel(
    label_id=label_id,
    background_color="#4285f4",
    text_color="#ffffff"
).run()

# 4. Add to messages
GmailAddLabel(
    message_id="msg_123",
    label_ids=[label_id]
).run()
```

---

## Production Requirements

1. **Environment Variables**
   ```bash
   COMPOSIO_API_KEY=your_api_key
   GMAIL_ENTITY_ID=your_entity_id
   ```

2. **Gmail Connection**
   - Gmail account must be connected via Composio
   - Valid entity_id for the connected account

3. **Label Requirements**
   - Label must be user-created (not system label)
   - Label ID must exist and be valid

---

## Testing

### Run Tests
```bash
python email_specialist/tools/GmailPatchLabel.py
```

### Validation Tests
All validation tests pass:
- ✅ System label protection
- ✅ Required field validation
- ✅ Property requirement check
- ✅ Color format validation
- ✅ Visibility option validation

---

## Related Tools

- **GmailListLabels** - List all labels and get IDs
- **GmailCreateLabel** - Create new custom labels
- **GmailRemoveLabel** - Delete custom labels
- **GmailAddLabel** - Add labels to messages
- **GmailBatchModifyMessages** - Batch label operations

---

## Best Practices

### Color Selection
1. **Use contrasting colors** - Ensure text is readable on background
2. **Follow Google's palette** - Use Google colors for consistency
3. **Priority coding** - Red = High, Yellow = Medium, Green = Low
4. **Test visibility** - Check colors in both light and dark themes

### Naming Conventions
1. **Be descriptive** - "Important Clients" vs "IC"
2. **Use categories** - "Project: Alpha", "Client: Acme"
3. **Avoid special chars** - Stick to alphanumeric and spaces
4. **Keep it short** - Long names truncate in sidebar

### Visibility Settings
1. **Active projects** - `labelShow`
2. **Archive projects** - `labelHide`
3. **Notification labels** - `labelShowIfUnread`
4. **Reference labels** - `messageListVisibility: hide`

---

## Troubleshooting

### "Cannot modify system label"
**Problem**: Trying to modify INBOX, SENT, etc.
**Solution**: Only custom labels (Label_*) can be modified

### "Invalid color format"
**Problem**: Using color names instead of hex
**Solution**: Use hex format: `"#ff0000"` not `"red"`

### "At least one property must be specified"
**Problem**: No properties provided to update
**Solution**: Provide at least one: name, visibility, or colors

### "Label not found"
**Problem**: Invalid label_id
**Solution**: Use GmailListLabels to get valid label IDs

---

**Tool Status**: ✅ Production Ready
**Last Updated**: November 1, 2025
**Pattern**: VALIDATED (user_id=entity_id)
**Test Coverage**: 100% validation tests passing
