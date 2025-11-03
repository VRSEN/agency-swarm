# CEO Gmail Routing - Quick Reference Guide
**For Developers**: Fast lookup for routing decisions

---

## Quick Tool Selection

### "Show me emails..."
| User Says | Gmail Query | Tool |
|-----------|-------------|------|
| "Show my emails" | `""` | GmailFetchEmails |
| "Unread emails" | `"is:unread"` | GmailFetchEmails |
| "Emails from john@example.com" | `"from:john@example.com"` | GmailFetchEmails |
| "Starred emails" | `"is:starred"` | GmailFetchEmails |
| "Emails about meeting" | `"subject:meeting"` | GmailFetchEmails |
| "Recent emails" | `"newer_than:3d"` | GmailFetchEmails |
| "Emails with attachments" | `"has:attachment"` | GmailFetchEmails |

### "Send/Draft email..."
| User Says | Action | Tool |
|-----------|--------|------|
| "Send email to X" | Immediate send | GmailSendEmail |
| "Draft email to X" | Create → Approve → Send | GmailCreateDraft → GmailSendDraft |
| "Compose message to X" | Create → Approve → Send | GmailCreateDraft → GmailSendDraft |
| "Send draft draft_123" | Send existing draft | GmailSendDraft |

### "Delete email..." ⚠️
| User Says | Action | Tool | Confirmation? |
|-----------|--------|------|---------------|
| "Delete email" | Move to trash (SAFE) | GmailMoveToTrash | NO |
| "Remove email" | Move to trash (SAFE) | GmailMoveToTrash | NO |
| "Trash this" | Move to trash (SAFE) | GmailMoveToTrash | NO |
| "Permanently delete" | Permanent (DANGEROUS) | GmailDeleteMessage | YES - Required |
| "Delete forever" | Permanent (DANGEROUS) | GmailDeleteMessage | YES - Required |

### "Organize emails..."
| User Says | Action | Tool |
|-----------|--------|------|
| "Mark as read" | Remove UNREAD label | GmailBatchModifyMessages |
| "Mark as unread" | Add UNREAD label | GmailBatchModifyMessages |
| "Star this" | Add STARRED label | GmailBatchModifyMessages |
| "Unstar this" | Remove STARRED label | GmailBatchModifyMessages |
| "Archive this" | Remove INBOX label | GmailBatchModifyMessages |
| "Label as Important" | Add IMPORTANT label | GmailAddLabel (single) |
| "Archive conversation" | Remove INBOX from thread | GmailModifyThreadLabels |

### "Find contact..."
| User Says | Action | Tool |
|-----------|--------|------|
| "Find John's email" | Search by name | GmailSearchPeople |
| "Who is john@example.com?" | Search by email | GmailSearchPeople |
| "Show all contacts" | List contacts | GmailGetContacts |
| "Get full contact details" | Search → Get details | GmailSearchPeople → GmailGetPeople |

---

## Safety Decision Tree

```
User Request
    ↓
Contains "permanently" or "forever"?
    ↓
  ┌─YES────────────────────────┐
  │                            │
  ↓                            ↓
HALT EXECUTION          Contains "delete"?
  ↓                            ↓
Present WARNING            ┌─YES─┐
  ↓                        ↓     ↓
Require confirmation   Move to   NO → Route
  ↓                    Trash           normally
Validate text          (GmailMoveToTrash)
  ↓
Correct? ("CONFIRM PERMANENT DELETE")
  ↓
┌─YES─────────────┐
│                 │
↓                 ↓
Execute      Cancel/Abort
GmailDeleteMessage
```

---

## Ambiguity Checklist

**Before executing, check:**

- [ ] Delete intent? → Confirm trash vs permanent
- [ ] Bulk operation (>10 items)? → Confirm count
- [ ] Multiple contacts match? → Ask user to select
- [ ] Message or thread operation? → Clarify scope
- [ ] Send immediately or draft? → Ask mode (default: draft)
- [ ] Missing context (message_id/thread_id)? → Request clarification
- [ ] Vague reference ("this", "that")? → Ask "which?"

---

## Common Workflows

### 1. Draft → Review → Send
```python
# Step 1: Create draft
draft = GmailCreateDraft(to=email, subject=subject, body=body)

# Step 2: Present to user
present_draft_to_user(draft)

# Step 3: Wait for approval
user_response = wait_for_user_input()

# Step 4: Handle response
if user_response == "send":
    GmailSendDraft(draft_id=draft.id)
elif user_response == "revise":
    ReviseEmailDraft(draft, changes)
    goto Step 2  # Present again
else:  # cancel
    # Keep draft or delete
```

### 2. Search → Organize → Report
```python
# Step 1: Search
emails = GmailFetchEmails(query=user_query)

# Step 2: Confirm if bulk
if len(emails) > 10:
    confirmed = confirm_bulk_operation(count=len(emails))
    if not confirmed:
        abort()

# Step 3: Execute
message_ids = extract_message_ids(emails)
GmailBatchModifyMessages(
    message_ids=message_ids,
    remove_label_ids=["INBOX"]  # Example: Archive
)

# Step 4: Report
report_to_user(f"Archived {len(emails)} emails")
```

### 3. Contact → Disambiguate → Email
```python
# Step 1: Search contact
results = GmailSearchPeople(query=name)

# Step 2: Disambiguate if multiple
if len(results) > 1:
    selected = present_options_and_wait(results)
    email = selected.email
elif len(results) == 1:
    email = results[0].email
else:  # No results
    email = ask_user_for_email()

# Step 3: Send email
GmailSendEmail(to=email, subject=subject, body=body)
```

### 4. Bulk Delete (Safe)
```python
# Step 1: Search
emails = GmailFetchEmails(query=criteria)

# Step 2: Present options
choice = ask_user(
    f"Found {len(emails)} emails. Move to trash or permanently delete?"
)

# Step 3: Execute based on choice
if choice == "trash":
    for message_id in extract_ids(emails):
        GmailMoveToTrash(message_id=message_id)
    report(f"Moved {len(emails)} to trash (recoverable)")

elif choice == "permanent":
    # CRITICAL: Confirm
    confirmed = require_exact_confirmation("CONFIRM PERMANENT DELETE")
    if confirmed:
        # Batch in groups of 100
        batches = split_into_batches(extract_ids(emails), size=100)
        for batch in batches:
            GmailBatchDeleteMessages(message_ids=batch)
        report(f"⚠️ {len(emails)} PERMANENTLY deleted")
    else:
        abort()
```

---

## Error Handling Quick Ref

| Error Code | Meaning | Action |
|------------|---------|--------|
| 401 | Auth failed | "Reconnect Gmail account" |
| 403 | Permission denied | "Update permissions: {scope}" |
| 404 | Not found | "Item may be deleted. Try search?" |
| 400 | Invalid params | "Let me try different approach" |
| 429 | Rate limit | Retry after {seconds} with backoff |
| 500 | Server error | Retry 3x with backoff |
| Timeout | Network issue | Retry with backoff |
| Empty results | No matches | "No results. Try different search?" |

---

## Gmail Query Operators

```
from:email           - Emails from specific sender
to:email             - Emails to specific recipient
subject:keyword      - Emails with keyword in subject
is:unread            - Unread emails
is:read              - Read emails
is:starred           - Starred emails
label:IMPORTANT      - Emails marked important
has:attachment       - Emails with attachments
newer_than:Xd        - Emails newer than X days
older_than:Xd        - Emails older than X days
before:YYYY/MM/DD    - Before specific date
after:YYYY/MM/DD     - After specific date

Combine with AND:
from:john@example.com subject:meeting is:unread
```

---

## Gmail Label IDs

### System Labels
```
INBOX               - In inbox
SENT                - Sent messages
DRAFT               - Draft messages
STARRED             - Starred messages
IMPORTANT           - Important messages
UNREAD              - Unread messages
TRASH               - In trash
SPAM                - Spam messages
```

### Custom Labels
```
Format: "Label_123"
Get IDs: GmailListLabels
Create: GmailCreateLabel(name="MyLabel")
```

---

## Safety Confirmation Templates

### Permanent Delete (Single)
```
⚠️ WARNING: PERMANENT DELETION

This will PERMANENTLY delete 1 email:
From: {sender}
Subject: {subject}
Date: {date}

- CANNOT be recovered
- NOT moved to trash
- Deletion is IRREVERSIBLE

Type 'CONFIRM PERMANENT DELETE' to proceed, or 'CANCEL' to abort.
```

### Permanent Delete (Bulk)
```
⚠️ WARNING: PERMANENT DELETION

This will PERMANENTLY delete {count} emails:
{list of first 5 emails}
... and {count - 5} more

- CANNOT be recovered
- NOT moved to trash
- Deletion is IRREVERSIBLE

Type 'CONFIRM PERMANENT DELETE' to proceed, or 'CANCEL' to abort.
```

### Bulk Operation
```
I found {count} emails matching your criteria:
{criteria description}

Proceed with {operation} on all {count} emails? (yes/no)
```

---

## Context Requirements

### Required Context by Tool

| Tool | Required Context | Optional Context |
|------|-----------------|------------------|
| GmailGetMessage | message_id | - |
| GmailMoveToTrash | message_id | - |
| GmailDeleteMessage | message_id | - |
| GmailFetchMessageByThreadId | thread_id | - |
| GmailModifyThreadLabels | thread_id | - |
| GmailAddLabel | message_id, label_ids | - |
| GmailBatchModifyMessages | message_ids | add_label_ids, remove_label_ids |
| GmailSendDraft | draft_id | - |
| GmailDeleteDraft | draft_id | - |
| GmailGetPeople | resource_name | person_fields |

### Context Extraction

```python
# From previous interaction
context = {
    "message_id": "msg_123",           # Last viewed email
    "thread_id": "thread_456",         # Current conversation
    "draft_id": "draft_789",           # Last created draft
    "resource_name": "people/c123",    # Last searched contact
    "message_ids": ["msg_1", "msg_2"] # Bulk operation targets
}

# Use in routing
if "this email" in user_input:
    message_id = context.get("message_id")
    if not message_id:
        ask_user("Which email?")
```

---

## Batch Operation Rules

### Batch Sizes
- **Max per batch**: 100 items (Gmail API limit)
- **Confirmation threshold**: 10 items
- **Progress reporting**: Every 25 items

### Batching Strategy
```python
def batch_operation(message_ids, operation):
    # Confirm if large
    if len(message_ids) > 10:
        if not confirm(count=len(message_ids)):
            return

    # Split into batches
    batches = [message_ids[i:i+100] for i in range(0, len(message_ids), 100)]

    # Execute batches
    for i, batch in enumerate(batches):
        operation(batch)

        # Report progress
        if len(batches) > 1:
            progress = (i + 1) / len(batches) * 100
            report_progress(f"{progress:.0f}% complete")
```

---

## Pattern Priority

When multiple patterns match:

1. **Exact tool reference** (e.g., user says "GmailFetchEmails") → Highest
2. **Explicit + Explicit** (e.g., "permanently delete msg_123") → High
3. **Explicit + Implied** (e.g., "delete this") → Medium
4. **Implied + Explicit** (e.g., "emails from john") → Medium
5. **Fuzzy/Ambiguous** (e.g., "show stuff") → Low (clarify)

---

## Confidence Thresholds

```python
if confidence >= 0.85:
    execute_directly()
elif confidence >= 0.60:
    ask_confirmation()
elif confidence >= 0.40:
    request_clarification()
else:  # < 0.40
    present_category_options()
```

---

## Testing Checklist

Before deploying routing logic:

- [ ] Test all 15 delete safety scenarios
- [ ] Test permanent delete requires "CONFIRM PERMANENT DELETE"
- [ ] Test bulk operations show count
- [ ] Test ambiguous delete defaults to trash
- [ ] Test contact disambiguation
- [ ] Test empty results handling
- [ ] Test error retries with backoff
- [ ] Test workflow state management
- [ ] Test context extraction
- [ ] Test batch splitting (>100 items)

---

## Performance Tips

### Caching
```python
# Cache label list (changes infrequently)
labels = cache.get("gmail_labels", ttl=3600)
if not labels:
    labels = GmailListLabels()
    cache.set("gmail_labels", labels, ttl=3600)

# Cache contact searches (30 min)
contacts = cache.get(f"contact_{query}", ttl=1800)
if not contacts:
    contacts = GmailSearchPeople(query=query)
    cache.set(f"contact_{query}", contacts, ttl=1800)
```

### Rate Limiting
```python
# Respect Gmail API limits
rate_limiter.wait_if_needed()  # Max 25 req/sec
result = GmailFetchEmails(...)

# Bulk operations - add delay
for batch in batches:
    GmailBatchModifyMessages(batch)
    sleep(1.0)  # 1 second between batches
```

---

## Common Mistakes to Avoid

❌ **Don't**: Default to permanent delete
✅ **Do**: Default to GmailMoveToTrash

❌ **Don't**: Execute bulk operations without confirmation
✅ **Do**: Show count and confirm if >10 items

❌ **Don't**: Accept "yes" for permanent delete confirmation
✅ **Do**: Require exact text "CONFIRM PERMANENT DELETE"

❌ **Don't**: Use GmailAddLabel for bulk operations
✅ **Do**: Use GmailBatchModifyMessages

❌ **Don't**: Exceed 100 items per batch
✅ **Do**: Split into multiple batches

❌ **Don't**: Assume context exists
✅ **Do**: Check for context and ask if missing

❌ **Don't**: Use GmailAddLabel for thread operations
✅ **Do**: Use GmailModifyThreadLabels for threads

❌ **Don't**: Ignore empty results
✅ **Do**: Provide helpful suggestions

---

## Debug Checklist

When routing fails:

1. **Check intent detection**: Was intent correctly identified?
2. **Check entity extraction**: Were emails, names, dates extracted?
3. **Check context**: Is required context (message_id, etc.) available?
4. **Check ambiguity**: Should clarification be requested?
5. **Check safety**: Does this need confirmation?
6. **Check tool selection**: Is the right tool chosen?
7. **Check parameters**: Are all required params provided?
8. **Check error handling**: Is error gracefully handled?

---

**END OF QUICK REFERENCE**

Keep this handy during development and debugging!
