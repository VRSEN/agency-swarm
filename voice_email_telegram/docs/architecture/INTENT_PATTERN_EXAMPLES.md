# Gmail Intent Pattern Examples
**Version**: 1.0
**Date**: 2025-11-01

This document provides 50+ real-world intent pattern examples for CEO agent routing.

---

## Category 1: Fetch/Search Intents (15 examples)

### Basic Fetch
```
User: "Show me my emails"
Intent: fetch_emails
Tool: GmailFetchEmails
Params: {query: "", max_results: 10}
```

```
User: "What are my recent emails?"
Intent: fetch_recent
Tool: GmailFetchEmails
Params: {query: "newer_than:3d", max_results: 10}
```

```
User: "List all my emails from today"
Intent: fetch_by_date
Tool: GmailFetchEmails
Params: {query: "newer_than:1d", max_results: 10}
```

### Filter by Status
```
User: "Show my unread emails"
Intent: fetch_unread
Tool: GmailFetchEmails
Params: {query: "is:unread", max_results: 10}
```

```
User: "What emails are starred?"
Intent: fetch_starred
Tool: GmailFetchEmails
Params: {query: "is:starred", max_results: 10}
```

```
User: "Show me important emails"
Intent: fetch_important
Tool: GmailFetchEmails
Params: {query: "label:IMPORTANT", max_results: 10}
```

### Filter by Sender
```
User: "Show emails from john@example.com"
Intent: fetch_from_sender
Tool: GmailFetchEmails
Params: {query: "from:john@example.com", max_results: 10}
Entities: {sender_email: "john@example.com"}
```

```
User: "What did Sarah send me?"
Intent: fetch_from_person
Workflow: GmailSearchPeople(query="Sarah") → Extract email → GmailFetchEmails(query="from:{email}")
```

```
User: "Emails from my boss"
Intent: fetch_from_contact
Workflow: Retrieve "boss" from context/preferences → GmailFetchEmails(query="from:{boss_email}")
```

### Filter by Content
```
User: "Find emails about the project"
Intent: fetch_by_subject
Tool: GmailFetchEmails
Params: {query: "subject:project", max_results: 10}
```

```
User: "Show me emails with 'invoice' in them"
Intent: fetch_by_keyword
Tool: GmailFetchEmails
Params: {query: "invoice", max_results: 10}
```

```
User: "Emails with attachments"
Intent: fetch_with_attachments
Tool: GmailFetchEmails
Params: {query: "has:attachment", max_results: 10}
```

### Complex Queries
```
User: "Unread emails from john@example.com about meeting"
Intent: fetch_complex
Tool: GmailFetchEmails
Params: {query: "from:john@example.com subject:meeting is:unread", max_results: 10}
```

```
User: "Starred emails from last week"
Intent: fetch_starred_recent
Tool: GmailFetchEmails
Params: {query: "is:starred newer_than:7d", max_results: 10}
```

```
User: "Emails from marketing team with attachments"
Intent: fetch_team_attachments
Tool: GmailFetchEmails
Params: {query: "from:*@marketing.company.com has:attachment", max_results: 10}
```

---

## Category 2: Read Intents (8 examples)

### Read Single Email
```
User: "Read the email from Sarah"
Intent: read_from_sender
Workflow: GmailFetchEmails(query="from:sarah") → Extract first message_id → GmailGetMessage(message_id)
```

```
User: "Open the latest email"
Intent: read_latest
Workflow: GmailFetchEmails(max_results=1) → GmailGetMessage(message_id)
```

```
User: "Show me message msg_12345"
Intent: read_by_id
Tool: GmailGetMessage
Params: {message_id: "msg_12345"}
```

### Read Thread/Conversation
```
User: "Show me this entire conversation"
Intent: read_thread
Tool: GmailFetchMessageByThreadId
Params: {thread_id: "{context.thread_id}"}
Context: Requires thread_id from previous interaction
```

```
User: "Read all messages in this thread"
Intent: read_full_thread
Tool: GmailFetchMessageByThreadId
Params: {thread_id: "{context.thread_id}"}
```

### Read with Attachment
```
User: "Download the PDF from this email"
Intent: get_attachment
Workflow: GmailGetMessage(message_id) → Extract attachment_id → GmailGetAttachment(message_id, attachment_id)
```

```
User: "Show me the attachments from john's email"
Intent: list_attachments
Workflow: GmailFetchEmails(query="from:john has:attachment") → GmailGetMessage → Extract attachment list
```

```
User: "Get the file from the latest email"
Intent: get_latest_attachment
Workflow: GmailFetchEmails(max_results=1) → GmailGetMessage → GmailGetAttachment
```

---

## Category 3: Send Intents (10 examples)

### Direct Send
```
User: "Send email to john@example.com about the meeting"
Intent: send_email
Tool: GmailSendEmail
Params: {
  to: "john@example.com",
  subject: "Meeting",
  body: "Composed from voice intent"
}
```

```
User: "Email Sarah and tell her I'll be late"
Intent: send_quick_message
Workflow: GmailSearchPeople(query="Sarah") → Extract email → GmailSendEmail(to=email, body="I'll be late")
```

```
User: "Send this email now"
Intent: send_immediate
Tool: GmailSendEmail
Context: Draft already created in conversation context
```

### Draft First
```
User: "Draft an email to the team"
Intent: create_draft
Tool: GmailCreateDraft
Workflow: Create draft → Present for approval → Wait for send confirmation
```

```
User: "Compose message to john@example.com"
Intent: compose_email
Tool: GmailCreateDraft
Workflow: Draft → Review → Approval → Send
```

```
User: "Write an email to my boss about vacation"
Intent: draft_to_contact
Workflow:
  1. Identify "boss" from contacts/preferences
  2. GmailCreateDraft(to={boss_email}, subject="Vacation")
  3. Present for review
```

### Send Draft
```
User: "Send the draft I created"
Intent: send_draft
Workflow: GmailListDrafts → Identify latest → GmailSendDraft(draft_id)
```

```
User: "Send draft draft_456"
Intent: send_draft_by_id
Tool: GmailSendDraft
Params: {draft_id: "draft_456"}
```

```
User: "Go ahead and send that email"
Intent: confirm_send_draft
Tool: GmailSendDraft
Context: draft_id from previous approval workflow
```

### Complex Send
```
User: "Send email to john@example.com and CC sarah@example.com about the project"
Intent: send_with_cc
Tool: GmailSendEmail
Params: {
  to: "john@example.com",
  cc: "sarah@example.com",
  subject: "Project",
  body: "..."
}
```

---

## Category 4: Organize Intents (12 examples)

### Mark Read/Unread
```
User: "Mark this as read"
Intent: mark_read
Tool: GmailBatchModifyMessages
Params: {
  message_ids: ["{context.message_id}"],
  remove_label_ids: ["UNREAD"]
}
```

```
User: "Mark all these emails as unread"
Intent: mark_unread_bulk
Tool: GmailBatchModifyMessages
Params: {
  message_ids: ["{context.message_ids}"],
  add_label_ids: ["UNREAD"]
}
```

```
User: "Mark emails from john as read"
Intent: mark_read_filtered
Workflow:
  1. GmailFetchEmails(query="from:john")
  2. Extract message_ids
  3. GmailBatchModifyMessages(message_ids, remove_label_ids=["UNREAD"])
```

### Star/Unstar
```
User: "Star this email"
Intent: star_message
Tool: GmailBatchModifyMessages
Params: {
  message_ids: ["{context.message_id}"],
  add_label_ids: ["STARRED"]
}
```

```
User: "Unstar these emails"
Intent: unstar_bulk
Tool: GmailBatchModifyMessages
Params: {
  message_ids: ["{context.message_ids}"],
  remove_label_ids: ["STARRED"]
}
```

### Archive
```
User: "Archive this email"
Intent: archive_single
Tool: GmailBatchModifyMessages
Params: {
  message_ids: ["{context.message_id}"],
  remove_label_ids: ["INBOX"]
}
```

```
User: "Archive this entire conversation"
Intent: archive_thread
Tool: GmailModifyThreadLabels
Params: {
  thread_id: "{context.thread_id}",
  remove_label_ids: ["INBOX"]
}
```

```
User: "Archive all emails from newsletters"
Intent: archive_filtered
Workflow:
  1. GmailFetchEmails(query="from:*newsletter*")
  2. Confirm bulk operation if > 10
  3. GmailBatchModifyMessages(message_ids, remove_label_ids=["INBOX"])
```

### Label Operations
```
User: "Label this as Important"
Intent: add_label_important
Tool: GmailAddLabel
Params: {
  message_id: "{context.message_id}",
  label_ids: ["IMPORTANT"]
}
```

```
User: "Add 'ProjectX' label to these emails"
Intent: add_custom_label
Workflow:
  1. GmailListLabels → Find "ProjectX" label_id
  2. If not found → GmailCreateLabel(name="ProjectX")
  3. GmailBatchModifyMessages(message_ids, add_label_ids=[label_id])
```

```
User: "Create a label called 'Urgent'"
Intent: create_label
Tool: GmailCreateLabel
Params: {name: "Urgent"}
```

```
User: "Label this conversation as Work"
Intent: label_thread
Workflow:
  1. GmailListLabels → Find "Work" label_id
  2. GmailModifyThreadLabels(thread_id, add_label_ids=[label_id])
```

---

## Category 5: Delete Intents (10 examples)

### Safe Delete (Trash)
```
User: "Delete this email"
Intent: delete_safe
Tool: GmailMoveToTrash
Params: {message_id: "{context.message_id}"}
Safety: DEFAULT to trash (recoverable)
```

```
User: "Remove this message"
Intent: delete_message
Tool: GmailMoveToTrash
Params: {message_id: "{context.message_id}"}
Safety: "Remove" defaults to safe trash
```

```
User: "Trash these emails"
Intent: trash_bulk
Workflow:
  1. For each message_id in context.message_ids:
  2.   GmailMoveToTrash(message_id)
  3. Report count trashed
```

```
User: "Delete all emails from spam@example.com"
Intent: delete_from_sender
Workflow:
  1. GmailFetchEmails(query="from:spam@example.com")
  2. Confirm bulk operation
  3. For each message_id: GmailMoveToTrash(message_id)
Safety: Defaults to trash, not permanent
```

### Permanent Delete (DANGEROUS)
```
User: "Permanently delete this email"
Intent: delete_permanent
Workflow:
  1. HALT EXECUTION
  2. Present WARNING: "⚠️ This will PERMANENTLY delete. Cannot be recovered."
  3. Require: "Type 'CONFIRM PERMANENT DELETE'"
  4. If confirmed → GmailDeleteMessage(message_id)
  5. If not → ABORT
Safety: MANDATORY confirmation
```

```
User: "Delete this email forever"
Intent: delete_forever
Workflow: Same as permanent delete (requires confirmation)
```

```
User: "Permanently delete emails older than 2020"
Intent: permanent_bulk_delete
Workflow:
  1. GmailFetchEmails(query="before:2020/01/01")
  2. Show count and date range
  3. CRITICAL WARNING
  4. Require explicit "CONFIRM PERMANENT DELETE"
  5. If confirmed:
     - Split into batches of 100
     - GmailBatchDeleteMessages for each batch
  6. Report count deleted with warning
Safety: Extra caution for bulk permanent delete
```

### Draft Delete
```
User: "Delete this draft"
Intent: delete_draft
Workflow:
  1. GmailGetDraft(draft_id)
  2. Show draft preview (to/subject/snippet)
  3. Confirm: "Delete this draft? (yes/no)"
  4. If yes → GmailDeleteDraft(draft_id)
Safety: Show preview before deleting
```

```
User: "Delete draft draft_789"
Intent: delete_draft_by_id
Workflow: Same as above with specific draft_id
```

```
User: "Clear all my drafts"
Intent: delete_all_drafts
Workflow:
  1. GmailListDrafts
  2. Show count
  3. Confirm: "Delete all {count} drafts? (yes/no)"
  4. If yes → For each: GmailDeleteDraft(draft_id)
Safety: Bulk confirmation required
```

---

## Category 6: Contact Intents (8 examples)

### Search Contacts
```
User: "Find John Smith's email"
Intent: search_contact_by_name
Tool: GmailSearchPeople
Params: {query: "John Smith", page_size: 10}
```

```
User: "Who is john@example.com?"
Intent: search_contact_by_email
Tool: GmailSearchPeople
Params: {query: "john@example.com", page_size: 10}
```

```
User: "Find contacts in marketing department"
Intent: search_contacts_by_dept
Tool: GmailSearchPeople
Params: {query: "marketing", page_size: 10}
```

```
User: "Search for Sarah"
Intent: search_contact_partial
Tool: GmailSearchPeople
Params: {query: "Sarah", page_size: 10}
Handling: May return multiple results → Disambiguation needed
```

### Get Contact Details
```
User: "Get John's full contact information"
Intent: get_contact_details
Workflow:
  1. GmailSearchPeople(query="John")
  2. If multiple → Ask user to select
  3. Extract resource_name
  4. GmailGetPeople(resource_name)
```

```
User: "Show me all details for this person"
Intent: get_person_profile
Tool: GmailGetPeople
Params: {resource_name: "{context.resource_name}"}
Context: Requires resource_name from search
```

### List Contacts
```
User: "Show all my contacts"
Intent: list_all_contacts
Tool: GmailGetContacts
Params: {}
```

```
User: "List my Gmail contacts"
Intent: list_contacts
Tool: GmailGetContacts
Params: {}
```

---

## Category 7: Ambiguous Intents (15 examples)

### Ambiguous Delete
```
User: "Delete emails from john@example.com"
Ambiguity: Trash or Permanent?
Resolution:
  CEO: "Would you like to:
    1. Move to trash (recoverable for 30 days) ← RECOMMENDED
    2. Permanently delete (CANNOT recover)
  Which would you prefer?"
Default: If no response, DEFAULT to trash
```

### Ambiguous Scope
```
User: "Label this as Important"
Ambiguity: This message or entire conversation?
Context: If thread_id available
Resolution:
  CEO: "Would you like to:
    1. Label just this message
    2. Label the entire conversation
  Which would you prefer?"
```

### Ambiguous Contact
```
User: "Email John about the meeting"
Ambiguity: Multiple Johns in contacts
Resolution:
  CEO: "I found 3 contacts named John:
    1. John Smith (john.smith@company.com) - Marketing
    2. John Doe (john.doe@company.com) - Engineering
    3. John Johnson (jjohnson@partner.com) - External
  Which John?"
```

### Ambiguous Send Mode
```
User: "Email Sarah about vacation"
Ambiguity: Send immediately or draft first?
Resolution:
  CEO: "Would you like me to:
    1. Create a draft for review first ← RECOMMENDED
    2. Send immediately
  Which would you prefer?"
Default: Draft mode (safer)
```

### Ambiguous Date
```
User: "Show me emails from last week"
Ambiguity: Previous 7 days or calendar week?
Resolution:
  Interpret: "last week" → "newer_than:7d" (rolling 7 days)
  Alternative: Ask for specific date range if critical
```

### Ambiguous Count
```
User: "Show me my emails"
Ambiguity: How many? All or recent?
Resolution:
  Default: max_results=10 (reasonable default)
  CEO: "Showing your 10 most recent emails. Need more? Say 'show 20' or 'show all'"
```

### Ambiguous Filter
```
User: "Show important emails"
Ambiguity: IMPORTANT label or starred?
Resolution:
  Interpret: "important" → label:IMPORTANT (Gmail's importance marker)
  Note: "starred" is different from "important"
```

### Ambiguous Archive
```
User: "Archive these"
Ambiguity: Which "these"? Messages or thread?
Context: Requires message_ids or thread_id from context
Resolution:
  If context.message_ids exists → Batch archive messages
  If context.thread_id exists → Archive thread
  If neither → Ask: "Which emails would you like to archive?"
```

### Ambiguous Subject
```
User: "Find emails about the project"
Ambiguity: Subject or body or both?
Resolution:
  Broad search: query="project" (searches both subject and body)
  Note: Gmail search is comprehensive by default
```

### Ambiguous Sender
```
User: "Emails from Sarah"
Ambiguity: Which Sarah? (if multiple Sarahs in contacts)
Resolution:
  1. GmailSearchPeople(query="Sarah")
  2. If 1 result → Use that email
  3. If multiple → Ask user to disambiguate
  4. If 0 → Ask for email address
```

### Ambiguous Time Range
```
User: "Show recent emails"
Ambiguity: How recent? Today? This week?
Resolution:
  Default: "recent" → "newer_than:3d" (last 3 days)
  CEO: "Showing emails from the last 3 days. Need a different range?"
```

### Ambiguous Operation
```
User: "Deal with these emails"
Ambiguity: Delete? Archive? Label? Mark read?
Resolution:
  CEO: "What would you like to do with these emails?
    - Archive them
    - Delete them
    - Mark as read
    - Label them
    - Something else?"
```

### Ambiguous Reference
```
User: "Delete that email"
Ambiguity: Which email? No context
Resolution:
  CEO: "Which email would you like to delete? You can say:
    - The latest email
    - Email from [person]
    - The email about [topic]"
```

### Ambiguous Attachment
```
User: "Get the file"
Ambiguity: Which file from which email?
Context: Requires message_id and attachment context
Resolution:
  CEO: "Which file would you like? From which email?"
```

### Ambiguous Label
```
User: "Label this"
Ambiguity: Which label to add?
Resolution:
  CEO: "Which label would you like to add? Your labels:
    - Important
    - Work
    - Personal
    - ProjectX
  Or create a new label?"
```

---

## Pattern Matching Priority

When multiple patterns match, use this priority order:

1. **Exact Tool Reference** (e.g., "GmailFetchEmails" mentioned) → Highest priority
2. **Explicit Operation + Explicit Target** (e.g., "permanently delete msg_123") → High priority
3. **Explicit Operation + Implied Target** (e.g., "delete this") → Medium priority
4. **Implied Operation + Explicit Target** (e.g., "emails from john") → Medium priority
5. **Fuzzy/Ambiguous** (e.g., "show me stuff") → Low priority, requires clarification

---

## Confidence Scoring

```python
CONFIDENCE_THRESHOLDS = {
    "high": 0.85,    # Execute directly
    "medium": 0.60,  # Ask for confirmation
    "low": 0.40,     # Request clarification
    "very_low": 0.0  # Present category options
}

CONFIDENCE_FACTORS = {
    "exact_keyword_match": +0.3,
    "entity_extracted": +0.2,
    "context_available": +0.15,
    "single_pattern_match": +0.25,
    "multiple_pattern_match": -0.1,  # Ambiguity penalty
    "unknown_entity": -0.2,
    "missing_context": -0.15
}
```

---

**END OF INTENT PATTERN EXAMPLES**

Total Examples: 78 intent patterns across 7 categories + 15 ambiguity scenarios
