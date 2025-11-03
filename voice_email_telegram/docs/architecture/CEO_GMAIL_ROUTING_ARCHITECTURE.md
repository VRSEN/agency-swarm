# CEO Gmail Routing Architecture
**Version**: 1.0
**Date**: 2025-11-01
**Author**: Backend Architect Agent

## Executive Summary

This document defines the comprehensive routing architecture for the CEO agent to orchestrate 25 Gmail tools across 7 functional categories. The architecture implements intent detection, decision trees, safety protocols, workflow patterns, and error handling to enable natural voice-to-email operations.

---

## 1. Tool Inventory & Categories

### 1.1 Fetch/Read Operations (5 tools)
| Tool | Purpose | Primary Use Case |
|------|---------|------------------|
| `GmailFetchEmails` | Search and fetch emails with Gmail query operators | "Show me emails from john@example.com" |
| `GmailGetMessage` | Retrieve single message by ID | "Read email ID msg_123" |
| `GmailFetchMessageByThreadId` | Fetch all messages in a thread | "Show me this entire conversation" |
| `GmailListThreads` | List email threads with filters | "Show my recent conversations" |
| `GmailGetAttachment` | Download email attachment | "Get the PDF from this email" |

### 1.2 Draft Management (5 tools)
| Tool | Purpose | Primary Use Case |
|------|---------|------------------|
| `GmailCreateDraft` | Create email draft | "Draft an email to Sarah" |
| `GmailGetDraft` | Retrieve draft by ID | "Show me draft draft_456" |
| `GmailListDrafts` | List all drafts | "What drafts do I have?" |
| `GmailSendDraft` | Send existing draft | "Send draft draft_456" |
| `GmailDeleteDraft` | Delete draft | "Delete draft draft_456" |

### 1.3 Send Operations (2 tools)
| Tool | Purpose | Primary Use Case |
|------|---------|------------------|
| `GmailSendEmail` | Send email directly | "Send email to john@example.com" |
| `GmailSendDraft` | Send existing draft | "Send the draft I created" |

### 1.4 Label Management (6 tools)
| Tool | Purpose | Primary Use Case |
|------|---------|------------------|
| `GmailListLabels` | List all available labels | "What labels do I have?" |
| `GmailCreateLabel` | Create new custom label | "Create label 'ProjectX'" |
| `GmailAddLabel` | Add label to single message | "Label this email as Important" |
| `GmailRemoveLabel` | Remove label from message (DEPRECATED) | Use `GmailBatchModifyMessages` instead |
| `GmailPatchLabel` | Update label properties | "Rename label 'Work' to 'Office'" |
| `GmailModifyThreadLabels` | Add/remove labels on entire thread | "Archive this conversation" |

### 1.5 Delete Operations (4 tools)
| Tool | Purpose | Safety Level | Use Case |
|------|---------|--------------|----------|
| `GmailMoveToTrash` | Soft delete (recoverable 30 days) | SAFE | "Delete this email" |
| `GmailDeleteMessage` | Permanent delete (CANNOT recover) | DANGEROUS | "Permanently delete this" |
| `GmailBatchDeleteMessages` | Bulk permanent delete | DANGEROUS | "Permanently delete these 50 emails" |
| `GmailDeleteDraft` | Delete draft | SAFE | "Delete this draft" |

### 1.6 Batch Operations (2 tools)
| Tool | Purpose | Primary Use Case |
|------|---------|------------------|
| `GmailBatchModifyMessages` | Bulk label add/remove on messages | "Mark these 10 emails as read" |
| `GmailBatchDeleteMessages` | Bulk permanent delete | "Permanently delete these emails" |

### 1.7 Contact Management (3 tools)
| Tool | Purpose | Primary Use Case |
|------|---------|------------------|
| `GmailSearchPeople` | Search contacts by name/email | "Find John Smith's email" |
| `GmailGetPeople` | Get detailed contact info | "Get full details for resource people/c123" |
| `GmailGetContacts` | List all contacts | "Show all my contacts" |

### 1.8 Profile (1 tool)
| Tool | Purpose | Primary Use Case |
|------|---------|------------------|
| `GmailGetProfile` | Get user's Gmail profile info | "What's my Gmail address?" |

---

## 2. Intent Detection Architecture

### 2.1 Intent Pattern Matching

#### Fetch/Search Intent Patterns
```python
FETCH_INTENT_PATTERNS = {
    # Basic fetch
    "show.*emails": "GmailFetchEmails",
    "list.*emails": "GmailFetchEmails",
    "what.*emails": "GmailFetchEmails",
    "get.*emails": "GmailFetchEmails",
    "find.*emails": "GmailFetchEmails",
    "search.*emails": "GmailFetchEmails",

    # Unread emails
    "unread.*emails": "GmailFetchEmails(query='is:unread')",
    "what.*unread": "GmailFetchEmails(query='is:unread')",
    "show.*unread": "GmailFetchEmails(query='is:unread')",

    # Emails from person
    "emails from (.+)": "GmailFetchEmails(query='from:{person}')",
    "messages from (.+)": "GmailFetchEmails(query='from:{person}')",

    # Starred emails
    "starred.*emails": "GmailFetchEmails(query='is:starred')",
    "important.*emails": "GmailFetchEmails(query='label:IMPORTANT')",

    # Attachments
    "emails.*attachments": "GmailFetchEmails(query='has:attachment')",
    "messages.*attachments": "GmailFetchEmails(query='has:attachment')",

    # Subject search
    "emails about (.+)": "GmailFetchEmails(query='subject:{topic}')",
    "find.*subject (.+)": "GmailFetchEmails(query='subject:{topic}')",

    # Date-based
    "recent.*emails": "GmailFetchEmails(query='newer_than:3d')",
    "today.*emails": "GmailFetchEmails(query='newer_than:1d')",
    "this week.*emails": "GmailFetchEmails(query='newer_than:7d')",
}
```

#### Read Intent Patterns
```python
READ_INTENT_PATTERNS = {
    # Single message
    "read.*email": "GmailFetchEmails → GmailGetMessage",
    "show.*email from (.+)": "GmailFetchEmails(query='from:{person}') → GmailGetMessage",
    "open.*message": "GmailGetMessage",

    # Thread/conversation
    "read.*conversation": "GmailListThreads → GmailFetchMessageByThreadId",
    "show.*thread": "GmailFetchMessageByThreadId",
    "entire.*conversation": "GmailFetchMessageByThreadId",
}
```

#### Send Intent Patterns
```python
SEND_INTENT_PATTERNS = {
    # Direct send (immediate)
    "send email to (.+)": "GmailSendEmail",
    "send message to (.+)": "GmailSendEmail",
    "email (.+) about (.+)": "GmailSendEmail",

    # Draft then send (preview)
    "draft email to (.+)": "GmailCreateDraft → APPROVAL → GmailSendDraft",
    "draft message to (.+)": "GmailCreateDraft → APPROVAL → GmailSendDraft",
    "compose email to (.+)": "GmailCreateDraft → APPROVAL → GmailSendDraft",

    # Send existing draft
    "send.*draft": "GmailListDrafts → GmailSendDraft",
    "send draft (.+)": "GmailSendDraft(draft_id={id})",
}
```

#### Organize Intent Patterns
```python
ORGANIZE_INTENT_PATTERNS = {
    # Mark read/unread
    "mark.*read": "GmailBatchModifyMessages(remove_label_ids=['UNREAD'])",
    "mark.*unread": "GmailBatchModifyMessages(add_label_ids=['UNREAD'])",

    # Star/unstar
    "star.*this": "GmailBatchModifyMessages(add_label_ids=['STARRED'])",
    "unstar.*this": "GmailBatchModifyMessages(remove_label_ids=['STARRED'])",

    # Archive
    "archive.*this": "GmailBatchModifyMessages(remove_label_ids=['INBOX'])",
    "archive.*emails": "GmailFetchEmails → GmailBatchModifyMessages(remove_label_ids=['INBOX'])",

    # Label operations
    "label.*as (.+)": "GmailAddLabel",
    "add label (.+)": "GmailAddLabel",
    "create label (.+)": "GmailCreateLabel",

    # Thread operations
    "archive.*conversation": "GmailModifyThreadLabels(remove_label_ids=['INBOX'])",
    "star.*conversation": "GmailModifyThreadLabels(add_label_ids=['STARRED'])",
}
```

#### Delete Intent Patterns (CRITICAL - Safety Required)
```python
DELETE_INTENT_PATTERNS = {
    # SAFE DELETE (default to trash)
    "delete.*email": "GmailMoveToTrash",  # DEFAULT TO SAFE
    "delete.*message": "GmailMoveToTrash",  # DEFAULT TO SAFE
    "remove.*email": "GmailMoveToTrash",  # DEFAULT TO SAFE
    "trash.*this": "GmailMoveToTrash",
    "get rid of.*this": "GmailMoveToTrash",

    # DANGEROUS DELETE (permanent) - REQUIRES CONFIRMATION
    "permanently delete": "CONFIRM → GmailDeleteMessage",
    "delete forever": "CONFIRM → GmailDeleteMessage",
    "delete.*permanently": "CONFIRM → GmailDeleteMessage",

    # BULK DELETE - REQUIRES CONFIRMATION
    "delete all.*from (.+)": "CONFIRM → GmailFetchEmails → GmailBatchDeleteMessages",
    "delete.*older than (.+)": "CONFIRM → GmailFetchEmails → GmailBatchDeleteMessages",

    # DRAFT DELETE (safe)
    "delete.*draft": "GmailDeleteDraft",
}
```

#### Contact Intent Patterns
```python
CONTACT_INTENT_PATTERNS = {
    # Search contacts
    "find.*email.*for (.+)": "GmailSearchPeople(query={name})",
    "who is (.+@.+)": "GmailSearchPeople(query={email})",
    "search.*contacts.*(.+)": "GmailSearchPeople(query={query})",

    # Get contact details
    "get.*contact.*details": "GmailSearchPeople → GmailGetPeople",
    "show.*full.*profile": "GmailGetPeople",

    # List contacts
    "show.*all.*contacts": "GmailGetContacts",
    "list.*my.*contacts": "GmailGetContacts",
}
```

### 2.2 Ambiguous Intent Resolution

#### Decision Matrix for Ambiguous Intents

| User Says | Ambiguity | Resolution Strategy |
|-----------|-----------|---------------------|
| "Delete emails from spam@example.com" | Trash vs Permanent? | DEFAULT to `GmailMoveToTrash` (safer) |
| "Delete this" | Single vs Bulk? Thread vs Message? | Determine from context (message_id vs thread_id) |
| "Label this" | Message vs Thread? | If thread_id available → `GmailModifyThreadLabels`, else `GmailAddLabel` |
| "Mark as read" | Single vs Bulk? | If multiple message_ids → `GmailBatchModifyMessages`, else `GmailAddLabel` |
| "Archive" | Message vs Thread? | If user said "conversation" → `GmailModifyThreadLabels`, else `GmailBatchModifyMessages` |
| "Send email to John" | Draft first or direct? | If user said "send" → Direct send, if "draft"/"compose" → Draft workflow |

#### Clarification Prompts

```python
CLARIFICATION_PROMPTS = {
    "delete_ambiguous": {
        "prompt": "Do you want to move to trash (recoverable) or permanently delete (cannot recover)?",
        "options": {
            "trash": "GmailMoveToTrash",
            "permanent": "CONFIRM → GmailDeleteMessage"
        }
    },

    "scope_ambiguous": {
        "prompt": "Do you want to apply this to the single message or the entire conversation?",
        "options": {
            "message": "GmailAddLabel / GmailBatchModifyMessages",
            "conversation": "GmailModifyThreadLabels"
        }
    },

    "send_mode_ambiguous": {
        "prompt": "Would you like me to send this immediately or create a draft for review?",
        "options": {
            "send": "GmailSendEmail",
            "draft": "GmailCreateDraft → APPROVAL → GmailSendDraft"
        }
    },

    "bulk_confirm": {
        "prompt": "I found {count} emails matching your criteria. Do you want to proceed with this operation on all {count} emails?",
        "options": {
            "yes": "Proceed with bulk operation",
            "no": "Cancel operation"
        }
    }
}
```

---

## 3. Routing Decision Trees

### 3.1 Fetch/Read Decision Tree

```
User Intent: Fetch/Read Emails
│
├─ No specific filters?
│  └─> GmailFetchEmails(query="", max_results=10)
│
├─ Filter by sender?
│  ├─> Extract email from query
│  └─> GmailFetchEmails(query="from:{email}")
│
├─ Filter by unread?
│  └─> GmailFetchEmails(query="is:unread")
│
├─ Filter by date?
│  ├─> Extract date range
│  └─> GmailFetchEmails(query="newer_than:{days}d")
│
├─ Filter by subject?
│  ├─> Extract keywords
│  └─> GmailFetchEmails(query="subject:{keywords}")
│
├─ Filter by attachments?
│  └─> GmailFetchEmails(query="has:attachment")
│
├─ Read specific message?
│  ├─> Have message_id?
│  │   └─> GmailGetMessage(message_id)
│  └─> Need to search first?
│      └─> GmailFetchEmails → Extract message_id → GmailGetMessage
│
└─ Read entire thread?
   ├─> Have thread_id?
   │   └─> GmailFetchMessageByThreadId(thread_id)
   └─> Need to search first?
       └─> GmailListThreads → Extract thread_id → GmailFetchMessageByThreadId
```

### 3.2 Delete Decision Tree (CRITICAL SAFETY)

```
User Intent: Delete
│
├─ Does intent include "permanently" or "forever"?
│  ├─> YES
│  │   ├─> CONFIRMATION REQUIRED
│  │   │   ├─> User confirms?
│  │   │   │   ├─> Single message?
│  │   │   │   │   └─> GmailDeleteMessage(message_id)
│  │   │   │   └─> Multiple messages?
│  │   │   │       ├─> Count <= 100?
│  │   │   │       │   └─> GmailBatchDeleteMessages(message_ids)
│  │   │   │       └─> Count > 100?
│  │   │   │           └─> Split into batches → GmailBatchDeleteMessages (multiple calls)
│  │   │   └─> User cancels?
│  │   │       └─> ABORT operation
│  │   └─> NO CONFIRMATION
│  │       └─> ABORT operation (SAFETY: Never permanent delete without confirm)
│  │
│  └─> NO (regular "delete")
│      ├─> DEFAULT TO SAFE: GmailMoveToTrash
│      ├─> Single message?
│      │   └─> GmailMoveToTrash(message_id)
│      └─> Multiple messages?
│          ├─> Extract all message_ids
│          └─> Call GmailMoveToTrash for each (no batch trash tool)
│
└─ Delete draft?
   └─> GmailDeleteDraft(draft_id)
```

### 3.3 Label Management Decision Tree

```
User Intent: Label Operation
│
├─> List labels?
│   └─> GmailListLabels()
│
├─> Create new label?
│   ├─> Extract label name
│   └─> GmailCreateLabel(name={label_name})
│
├─> Add label?
│   ├─> Single message?
│   │   ├─> Have message_id?
│   │   │   └─> GmailAddLabel(message_id, label_ids)
│   │   └─> Need to search first?
│   │       └─> GmailFetchEmails → Extract message_id → GmailAddLabel
│   │
│   ├─> Entire thread/conversation?
│   │   ├─> Have thread_id?
│   │   │   └─> GmailModifyThreadLabels(thread_id, add_label_ids)
│   │   └─> Need to search first?
│   │       └─> GmailListThreads → Extract thread_id → GmailModifyThreadLabels
│   │
│   └─> Multiple messages (bulk)?
│       ├─> Have message_ids?
│       │   └─> GmailBatchModifyMessages(message_ids, add_label_ids)
│       └─> Need to search first?
│           └─> GmailFetchEmails → Extract message_ids → GmailBatchModifyMessages
│
└─> Remove label?
    ├─> Single message?
    │   └─> GmailBatchModifyMessages(message_ids, remove_label_ids)  # No dedicated RemoveLabel
    │
    ├─> Entire thread?
    │   └─> GmailModifyThreadLabels(thread_id, remove_label_ids)
    │
    └─> Multiple messages?
        └─> GmailBatchModifyMessages(message_ids, remove_label_ids)
```

### 3.4 Send/Draft Decision Tree

```
User Intent: Send Email
│
├─> User says "send" (immediate)?
│   ├─> Have all required info (to, subject, body)?
│   │   └─> GmailSendEmail(to, subject, body)
│   └─> Missing info?
│       └─> Ask for missing details → GmailSendEmail
│
├─> User says "draft" or "compose" (preview)?
│   ├─> Create draft first
│   │   └─> GmailCreateDraft(to, subject, body)
│   ├─> Present to user for review
│   │   ├─> User approves?
│   │   │   └─> GmailSendDraft(draft_id)
│   │   ├─> User requests changes?
│   │   │   └─> ReviseEmailDraft → Update draft → Present again
│   │   └─> User cancels?
│   │       └─> Keep draft or delete? → GmailDeleteDraft
│   └─> APPROVAL WORKFLOW
│
└─> Ambiguous (no explicit "send" or "draft")?
    ├─> Default behavior: DRAFT MODE (safer)
    ├─> Create draft
    ├─> Present for approval
    └─> Wait for user confirmation before sending
```

### 3.5 Contact Search Decision Tree

```
User Intent: Find Contact
│
├─> Search by name?
│   ├─> Full name (e.g., "John Smith")?
│   │   └─> GmailSearchPeople(query="John Smith")
│   └─> Partial name (e.g., "John")?
│       └─> GmailSearchPeople(query="John")
│
├─> Search by email?
│   └─> GmailSearchPeople(query="{email}")
│
├─> Need full contact details?
│   ├─> Have resource_name?
│   │   └─> GmailGetPeople(resource_name)
│   └─> Need to search first?
│       └─> GmailSearchPeople → Extract resource_name → GmailGetPeople
│
└─> List all contacts?
    └─> GmailGetContacts()
```

---

## 4. Safety Confirmation Flows

### 4.1 Permanent Deletion Confirmation (CRITICAL)

```
PERMANENT_DELETE_FLOW:
1. User requests permanent deletion
   Example: "Permanently delete emails from spam@example.com"

2. HALT EXECUTION - Mandatory confirmation required

3. Present WARNING to user:
   "⚠️ WARNING: PERMANENT DELETION

   This will PERMANENTLY delete {count} email(s).
   - CANNOT be recovered
   - NOT moved to trash
   - Deletion is IRREVERSIBLE

   Messages to be deleted:
   {list of subjects/senders}

   Type 'CONFIRM PERMANENT DELETE' to proceed, or 'CANCEL' to abort."

4. Wait for user response
   a. User types "CONFIRM PERMANENT DELETE":
      → Proceed with GmailDeleteMessage or GmailBatchDeleteMessages
      → Report success with warning

   b. User types anything else:
      → ABORT operation
      → Suggest safer alternative: "Would you like to move to trash instead?"

5. Post-deletion report:
   "⚠️ {count} email(s) PERMANENTLY deleted. Cannot be recovered."
```

### 4.2 Bulk Operation Confirmation

```
BULK_OPERATION_FLOW:
1. User requests bulk operation
   Example: "Mark all emails from john@example.com as read"

2. Execute search to determine count
   GmailFetchEmails(query="from:john@example.com")

3. If count > THRESHOLD (default: 10):
   a. Present confirmation:
      "I found {count} emails matching your criteria:
      - From: john@example.com
      - Operation: Mark as read

      Proceed with this operation on all {count} emails? (yes/no)"

   b. Wait for user response
      - "yes" → Proceed with GmailBatchModifyMessages
      - "no" → ABORT operation

4. Execute operation with progress updates:
   "Processing {count} emails..."
   "Completed: {count} emails marked as read."
```

### 4.3 Draft Deletion Safety

```
DRAFT_DELETE_FLOW:
1. User requests draft deletion
   Example: "Delete draft draft_456"

2. Fetch draft to show user
   GmailGetDraft(draft_id="draft_456")

3. Present draft details:
   "Draft to delete:
   To: {recipient}
   Subject: {subject}
   Preview: {first 100 chars}

   Delete this draft? (yes/no)"

4. Wait for user response
   - "yes" → GmailDeleteDraft(draft_id)
   - "no" → ABORT

5. Report: "Draft deleted successfully."
```

### 4.4 Label Deletion Safety

```
LABEL_DELETE_FLOW:
1. User requests label deletion
   Example: "Delete label 'OldProject'"

2. Check if label is system label
   If label in [INBOX, SENT, STARRED, etc.]:
      → ABORT: "Cannot delete system label '{label}'"

3. Count messages with this label
   GmailFetchEmails(query="label:{label_id}")

4. Present confirmation:
   "{count} emails currently have label '{label_name}'.

   Deleting this label will:
   - Remove label from all {count} emails
   - Delete the label permanently
   - NOT delete the emails themselves

   Proceed? (yes/no)"

5. Wait for user response
   - "yes" → GmailRemoveLabel (or API equivalent)
   - "no" → ABORT
```

---

## 5. Multi-Step Workflow Patterns

### 5.1 Create → Review → Send Workflow

```
DRAFT_WORKFLOW:
Step 1: Create Draft
   User: "Draft an email to sarah@company.com about the meeting"
   → Parse intent: to=sarah@company.com, topic="meeting"
   → Delegate to Email Specialist: DraftEmailFromVoice
   → Result: Draft created with draft_id="draft_123"

Step 2: Present for Review
   CEO: "Here's the draft I created:

   To: sarah@company.com
   Subject: Meeting Discussion
   Body: [draft content]

   Would you like to:
   - Send it now
   - Make changes
   - Cancel"

Step 3a: User Approves (Send)
   User: "Send it"
   → GmailSendDraft(draft_id="draft_123")
   → Report: "Email sent successfully. Message ID: msg_789"

Step 3b: User Requests Changes
   User: "Make the subject more specific"
   → Delegate to Email Specialist: ReviseEmailDraft
   → Update draft
   → Return to Step 2 (present again)

Step 3c: User Cancels
   User: "Cancel, I'll send it later"
   → Keep draft
   → Report: "Draft saved. You can send it later with 'send draft draft_123'"
```

### 5.2 Search → Get Details → Email Workflow

```
CONTACT_TO_EMAIL_WORKFLOW:
Step 1: Find Contact
   User: "Send an email to John from marketing"
   → Parse: Need to find John's email
   → GmailSearchPeople(query="John marketing")
   → Results: [
       {name: "John Smith", email: "john.smith@company.com", dept: "Marketing"},
       {name: "John Doe", email: "john.doe@company.com", dept: "Marketing"}
     ]

Step 2: Disambiguate (if multiple matches)
   CEO: "I found 2 Johns in marketing:
   1. John Smith (john.smith@company.com)
   2. John Doe (john.doe@company.com)

   Which one?"

   User: "John Smith"
   → Selected email: john.smith@company.com

Step 3: Get Full Contact Details (optional)
   → GmailGetPeople(resource_name="people/c123")
   → Extract: full_name, title, department

Step 4: Create Email
   → Continue to DRAFT_WORKFLOW
   → GmailCreateDraft(to="john.smith@company.com")
```

### 5.3 Fetch → Organize → Archive Workflow

```
ORGANIZE_EMAILS_WORKFLOW:
Step 1: Fetch Emails
   User: "Archive all emails from newsletters older than 30 days"
   → Parse: query="from:*newsletter* older_than:30d"
   → GmailFetchEmails(query="from:*newsletter* older_than:30d")
   → Results: 45 emails

Step 2: Confirm Bulk Operation
   CEO: "I found 45 emails from newsletters older than 30 days.

   Would you like to:
   - Archive all 45 (move to archive, keep accessible)
   - Delete all 45 (move to trash, recoverable for 30 days)
   - Permanently delete all 45 (cannot recover)
   - Cancel"

   User: "Archive all"

Step 3: Extract Message IDs
   → Extract message_ids from fetch results
   → message_ids = ["msg_1", "msg_2", ..., "msg_45"]

Step 4: Execute Archive
   → GmailBatchModifyMessages(
       message_ids=message_ids,
       remove_label_ids=["INBOX"]
     )

Step 5: Report
   CEO: "Archived 45 emails from newsletters.
   They're no longer in your inbox but remain accessible in All Mail."
```

### 5.4 Bulk Delete with Safety

```
BULK_DELETE_WORKFLOW:
Step 1: User Intent
   User: "Delete all emails from spam@example.com"
   → Detect: Bulk deletion request

Step 2: Fetch Matching Emails
   → GmailFetchEmails(query="from:spam@example.com", max_results=100)
   → Results: 73 emails

Step 3: Present for Confirmation
   CEO: "I found 73 emails from spam@example.com.

   Deletion options:
   - Move to trash (recoverable for 30 days) ← RECOMMENDED
   - Permanently delete (CANNOT recover)
   - Cancel

   Which would you prefer?"

   User: "Move to trash"

Step 4: Execute Safe Delete
   → Extract message_ids
   → For each message_id in message_ids:
       GmailMoveToTrash(message_id)  # No batch trash API
   → Track progress

Step 5: Report
   CEO: "Moved 73 emails from spam@example.com to trash.
   You can recover them from trash within 30 days if needed."

Alternative Step 3 (Permanent Delete):
   User: "Permanently delete"

   CEO: "⚠️ CRITICAL WARNING ⚠️
   This will PERMANENTLY delete 73 emails. They CANNOT be recovered.

   Type 'CONFIRM PERMANENT DELETE' to proceed."

   User: "CONFIRM PERMANENT DELETE"

   → GmailBatchDeleteMessages(message_ids)
   → Report: "⚠️ 73 emails PERMANENTLY deleted. Cannot be recovered."
```

---

## 6. Error Handling & Fallback Strategies

### 6.1 Tool Not Found Error

```
ERROR: Tool not found for intent
CAUSE: User intent doesn't match any routing pattern

FALLBACK STRATEGY:
1. Log the unmatched intent
2. Attempt fuzzy matching against known patterns
3. If fuzzy match found:
   CEO: "Did you mean: {matched_intent}? (yes/no)"
   → If yes: Execute matched intent
   → If no: Continue to step 4
4. Ask user for clarification:
   CEO: "I'm not sure how to help with that. Did you want to:
   - Fetch emails
   - Send an email
   - Organize emails
   - Delete emails
   - Manage contacts
   - Something else?"
5. Based on user response, re-route

EXAMPLE:
User: "Show me letters from boss"
→ No exact match for "letters"
→ Fuzzy match: "letters" ≈ "emails"
CEO: "Did you mean 'show emails from boss'? (yes/no)"
User: "yes"
→ Route to GmailFetchEmails(query="from:boss")
```

### 6.2 Ambiguous Intent Error

```
ERROR: Multiple possible interpretations
CAUSE: Intent matches multiple routing patterns

FALLBACK STRATEGY:
1. Identify all possible interpretations
2. Present options to user with explanations
3. Wait for user selection
4. Execute selected interpretation

EXAMPLE:
User: "Delete this"
→ Ambiguous: Trash or Permanent? Message or Thread? Single or Bulk?

CEO: "I need clarification on 'delete this':
1. Move to trash (recoverable for 30 days) ← RECOMMENDED
2. Permanently delete (CANNOT recover)

Which would you prefer?"

User: "Move to trash"
→ Route to GmailMoveToTrash(message_id)
```

### 6.3 Missing Parameters Error

```
ERROR: Required parameters not provided
CAUSE: Tool requires params not extractable from user intent

FALLBACK STRATEGY:
1. Identify missing parameters
2. Ask user for specific information
3. Validate user response
4. Execute with complete parameters

EXAMPLE:
User: "Send an email"
→ Missing: to, subject, body

CEO: "I'd be happy to help send an email. I need a few details:
- Who should I send it to?
- What's the subject?
- What would you like to say?"

User: "Send to john@example.com, subject 'Meeting', tell him I'll be late"
→ Extract: to=john@example.com, subject="Meeting", body="I'll be late"
→ GmailSendEmail(to, subject, body)
```

### 6.4 API Error Handling

```
ERROR: Gmail API returns error
CAUSE: Network issue, auth failure, quota exceeded, invalid params

FALLBACK STRATEGY by Error Type:

1. AUTHENTICATION ERROR (401):
   CEO: "Gmail authentication failed. Please reconnect your Gmail account."
   → Provide reconnect instructions
   → Log error for admin

2. PERMISSION ERROR (403):
   CEO: "I don't have permission to perform this action.
   Required permission: {scope}
   Please update Gmail connection permissions."
   → Provide permission update link

3. RATE LIMIT ERROR (429):
   CEO: "Gmail API rate limit exceeded. Please try again in {retry_after} seconds."
   → Implement exponential backoff
   → Retry after delay

4. NOT FOUND ERROR (404):
   CEO: "The requested email/draft/label wasn't found. It may have been deleted."
   → Suggest alternative actions

5. INVALID PARAMETER ERROR (400):
   CEO: "Invalid request parameters. Let me try a different approach."
   → Log error details
   → Attempt alternative tool/params

6. SERVER ERROR (500):
   CEO: "Gmail is experiencing issues. Please try again in a moment."
   → Retry with exponential backoff (3 attempts)
   → If all fail: "Gmail is temporarily unavailable. Please try again later."

7. NETWORK ERROR:
   CEO: "Network connection error. Checking connectivity..."
   → Retry with backoff
   → If persists: "Unable to connect to Gmail. Please check your internet connection."
```

### 6.5 Validation Error Handling

```
ERROR: Invalid email address or params
CAUSE: User provided invalid data

FALLBACK STRATEGY:

1. EMAIL VALIDATION:
   User: "Send email to john.example.com"  # Missing @

   CEO: "The email address 'john.example.com' appears invalid.
   Did you mean 'john@example.com'? (yes/no/enter correct email)"

   → If yes: Use corrected email
   → If no: Ask for correct email
   → If custom: Use provided email

2. DATE VALIDATION:
   User: "Show emails from yesterday"
   → Parse: "yesterday" → Calculate date → newer_than:1d
   → If parse fails: Ask for specific date

3. COUNT VALIDATION:
   User: "Show me 500 emails"  # Exceeds max

   CEO: "Gmail limits results to 100 emails per request.
   Would you like:
   - First 100 emails
   - Multiple batches of 100
   - Refine search to reduce results"

4. LABEL VALIDATION:
   User: "Add label 'Project X' to this email"
   → Check if label exists
   → If not: "Label 'Project X' doesn't exist. Would you like to create it? (yes/no)"
```

### 6.6 Empty Result Handling

```
ERROR: No results found
CAUSE: Query returned 0 matches

FALLBACK STRATEGY:

1. SEARCH RETURNED NO RESULTS:
   User: "Show emails from xyz@example.com"
   → GmailFetchEmails(query="from:xyz@example.com")
   → Results: 0 emails

   CEO: "I didn't find any emails from xyz@example.com.

   Would you like to:
   - Search for a different sender
   - Check your spam folder
   - Search by subject or keyword instead"

2. CONTACT NOT FOUND:
   User: "Find John Smith's email"
   → GmailSearchPeople(query="John Smith")
   → Results: 0 contacts

   CEO: "I couldn't find 'John Smith' in your contacts.

   You could:
   - Try searching by email address
   - Search with a different name
   - Add them as a new contact"

3. DRAFT NOT FOUND:
   User: "Send draft draft_456"
   → GmailGetDraft(draft_id="draft_456")
   → Error: 404 Not Found

   CEO: "Draft draft_456 wasn't found. It may have been deleted or already sent.

   Would you like to:
   - List all available drafts
   - Create a new draft"
```

---

## 7. CEO Instructions Enhancement

### 7.1 Proposed CEO Instructions Structure

```markdown
# CEO Agent Instructions

## Role
You are the CEO orchestrator for a voice-to-email system. You coordinate the workflow between Voice Handler, Email Specialist, and Memory Manager to convert voice messages into professional emails AND manage comprehensive Gmail operations.

## Core Responsibilities
1. Receive user queries (voice or text) about email operations
2. Route requests to appropriate Gmail tools based on intent
3. Coordinate multi-step workflows with safety confirmations
4. Manage the approval state machine for draft-send workflows
5. Handle ambiguous intents with clarification prompts
6. Ensure user safety with confirmation flows for destructive operations
7. Provide clear status updates and error handling

## Gmail Tool Routing System

### Intent Detection & Routing
Use the following patterns to route user intents to appropriate tools:

#### FETCH/SEARCH INTENTS
- "show emails" → GmailFetchEmails(query="")
- "unread emails" → GmailFetchEmails(query="is:unread")
- "emails from {person}" → GmailFetchEmails(query="from:{email}")
- "starred emails" → GmailFetchEmails(query="is:starred")
- "emails about {topic}" → GmailFetchEmails(query="subject:{topic}")
- "recent emails" → GmailFetchEmails(query="newer_than:3d")
- "emails with attachments" → GmailFetchEmails(query="has:attachment")

#### READ INTENTS
- "read email from {person}" → GmailFetchEmails → GmailGetMessage
- "show conversation" → GmailListThreads → GmailFetchMessageByThreadId
- "get attachment" → GmailGetAttachment(message_id, attachment_id)

#### SEND INTENTS
- "send email to {person}" → GmailSendEmail (IMMEDIATE)
- "draft email to {person}" → GmailCreateDraft → APPROVAL → GmailSendDraft
- "send draft {id}" → GmailSendDraft

#### ORGANIZE INTENTS
- "mark as read" → GmailBatchModifyMessages(remove_label_ids=["UNREAD"])
- "mark as unread" → GmailBatchModifyMessages(add_label_ids=["UNREAD"])
- "star this" → GmailBatchModifyMessages(add_label_ids=["STARRED"])
- "archive" → GmailBatchModifyMessages(remove_label_ids=["INBOX"])
- "label as {label}" → GmailAddLabel (single) or GmailModifyThreadLabels (thread)

#### DELETE INTENTS (CRITICAL SAFETY)
⚠️ SAFETY RULES for Deletion:
1. DEFAULT to GmailMoveToTrash (safer, recoverable)
2. ONLY use GmailDeleteMessage/GmailBatchDeleteMessages for EXPLICIT "permanently" requests
3. ALWAYS confirm before permanent deletion
4. Present clear warnings about non-recoverable deletion

- "delete email" → GmailMoveToTrash (DEFAULT SAFE)
- "trash this" → GmailMoveToTrash
- "permanently delete" → CONFIRM → GmailDeleteMessage
- "delete forever" → CONFIRM → GmailDeleteMessage
- "delete draft" → GmailDeleteDraft (safe)

Permanent Delete Confirmation Template:
```
⚠️ WARNING: PERMANENT DELETION
This will PERMANENTLY delete {count} email(s).
- CANNOT be recovered
- NOT moved to trash
- Deletion is IRREVERSIBLE

Type 'CONFIRM PERMANENT DELETE' to proceed, or 'CANCEL' to abort.
```

#### CONTACT INTENTS
- "find {name}'s email" → GmailSearchPeople(query={name})
- "who is {email}" → GmailSearchPeople(query={email})
- "show contacts" → GmailGetContacts
- "get contact details" → GmailSearchPeople → GmailGetPeople

### Decision Logic for Ambiguous Intents

#### Delete: Trash vs Permanent
- If user says "delete" (no "permanently"/"forever") → DEFAULT to GmailMoveToTrash
- If user says "permanently delete" → REQUIRE CONFIRMATION → GmailDeleteMessage
- NEVER permanent delete without explicit confirmation

#### Scope: Single vs Thread vs Bulk
- If user says "this email" → Single message operation
- If user says "conversation" or "thread" → GmailModifyThreadLabels
- If user says "all" or "these emails" → Bulk operation (GmailBatchModifyMessages)

#### Send: Immediate vs Draft
- If user says "send email" → Immediate send (GmailSendEmail)
- If user says "draft" or "compose" → Draft workflow with approval
- If ambiguous → ASK: "Send immediately or create draft for review?"

### Multi-Step Workflows

#### Draft → Review → Send Workflow
1. User requests email creation
2. Delegate to Email Specialist: DraftEmailFromVoice
3. Present draft to user for review
4. Handle user response:
   - "Send it" → GmailSendDraft
   - "Make changes" → ReviseEmailDraft → Present again
   - "Cancel" → Keep or delete draft

#### Search → Organize → Report Workflow
1. User requests bulk organization (e.g., "archive all from john@example.com")
2. GmailFetchEmails to find matching emails
3. Present count for confirmation if > 10 emails
4. Execute bulk operation (GmailBatchModifyMessages)
5. Report success with count

#### Contact → Email Workflow
1. User wants to email someone by name
2. GmailSearchPeople to find contact
3. If multiple matches → Ask user to disambiguate
4. GmailGetPeople for full details (optional)
5. Proceed to email creation workflow

### Error Handling

#### Tool Not Found
1. Attempt fuzzy matching
2. If fuzzy match: "Did you mean {match}?"
3. If no match: Present category options (Fetch/Send/Organize/Delete/Contacts)

#### Missing Parameters
1. Identify missing required params
2. Ask user for specific information
3. Validate response
4. Execute with complete params

#### API Errors
- 401 Auth Error → "Please reconnect Gmail account"
- 403 Permission Error → "Missing permission: {scope}"
- 429 Rate Limit → "Please try again in {seconds} seconds"
- 404 Not Found → "Item not found, may have been deleted"
- 400 Invalid Params → "Invalid request, trying alternative approach"
- 500 Server Error → Retry with exponential backoff

#### Empty Results
- No emails found → Suggest alternative search or check spam
- Contact not found → Suggest search by email or different name
- Draft not found → Suggest list all drafts or create new

### Safety Confirmations Required

MANDATORY CONFIRMATIONS:
1. Permanent deletion (GmailDeleteMessage/GmailBatchDeleteMessages)
2. Bulk operations > 10 items
3. Label deletion (if label has messages)
4. Draft deletion (show draft preview first)

CONFIRMATION TEMPLATE:
```
Operation: {operation_name}
Impact: {count} items affected
Details: {specifics}

Proceed? (yes/no)
```

## Communication Style
- Be concise and action-oriented
- Clearly communicate workflow status
- Handle errors gracefully with helpful suggestions
- Ask for clarification when information is missing
- ALWAYS prioritize user safety over convenience
- Provide clear warnings for destructive operations

## Tools Available
- ApprovalStateMachine: Manage workflow state transitions
- WorkflowCoordinator: Determine next agent and actions
- 25 Gmail Tools: Full email management capabilities (see routing guide above)

## Key Principles
1. SAFETY FIRST: Default to safer options (trash vs permanent delete)
2. CONFIRM DESTRUCTIVE OPERATIONS: Never permanent delete without confirmation
3. CLEAR COMMUNICATION: Always explain what you're about to do
4. GRACEFUL ERROR HANDLING: Provide helpful alternatives when operations fail
5. EFFICIENT ROUTING: Use the most appropriate tool for each intent
6. MULTI-STEP COORDINATION: Break complex requests into manageable workflows
7. USER EMPOWERMENT: Present options when intent is ambiguous
```

---

## 8. Test Cases for Routing Validation

### 8.1 Fetch/Read Test Cases

```python
TEST_CASES_FETCH = [
    {
        "user_input": "Show me my emails",
        "expected_tool": "GmailFetchEmails",
        "expected_params": {"query": "", "max_results": 10},
        "pass_criteria": "Fetches recent emails with default params"
    },
    {
        "user_input": "What are my unread emails?",
        "expected_tool": "GmailFetchEmails",
        "expected_params": {"query": "is:unread", "max_results": 10},
        "pass_criteria": "Correctly applies unread filter"
    },
    {
        "user_input": "Show emails from john@example.com",
        "expected_tool": "GmailFetchEmails",
        "expected_params": {"query": "from:john@example.com", "max_results": 10},
        "pass_criteria": "Extracts email and builds correct query"
    },
    {
        "user_input": "Find emails about meeting from last week",
        "expected_tool": "GmailFetchEmails",
        "expected_params": {"query": "subject:meeting newer_than:7d", "max_results": 10},
        "pass_criteria": "Combines subject and date filters"
    },
    {
        "user_input": "Show me emails with attachments",
        "expected_tool": "GmailFetchEmails",
        "expected_params": {"query": "has:attachment", "max_results": 10},
        "pass_criteria": "Applies attachment filter"
    },
    {
        "user_input": "Read the email from Sarah",
        "expected_workflow": "GmailFetchEmails(query='from:sarah') → GmailGetMessage",
        "pass_criteria": "Executes two-step workflow: search then read"
    },
]
```

### 8.2 Send/Draft Test Cases

```python
TEST_CASES_SEND = [
    {
        "user_input": "Send email to john@example.com about the meeting",
        "expected_tool": "GmailSendEmail",
        "expected_params": {"to": "john@example.com", "subject": "Meeting", "body": "..."},
        "pass_criteria": "Immediately sends without draft"
    },
    {
        "user_input": "Draft an email to sarah@company.com",
        "expected_workflow": "GmailCreateDraft → APPROVAL → GmailSendDraft",
        "pass_criteria": "Creates draft and waits for approval"
    },
    {
        "user_input": "Send draft draft_456",
        "expected_tool": "GmailSendDraft",
        "expected_params": {"draft_id": "draft_456"},
        "pass_criteria": "Sends existing draft directly"
    },
    {
        "user_input": "Compose email to marketing team",
        "expected_workflow": "GmailCreateDraft → APPROVAL → GmailSendDraft",
        "pass_criteria": "'Compose' triggers draft workflow"
    },
]
```

### 8.3 Delete Safety Test Cases (CRITICAL)

```python
TEST_CASES_DELETE = [
    {
        "user_input": "Delete this email",
        "expected_tool": "GmailMoveToTrash",
        "expected_params": {"message_id": "msg_123"},
        "pass_criteria": "DEFAULTS to safe trash, not permanent delete"
    },
    {
        "user_input": "Permanently delete this email",
        "expected_flow": "CONFIRMATION_PROMPT → (if confirmed) GmailDeleteMessage",
        "pass_criteria": "REQUIRES confirmation before permanent delete"
    },
    {
        "user_input": "Delete all emails from spam@example.com",
        "expected_flow": "GmailFetchEmails → CONFIRMATION → GmailMoveToTrash (loop)",
        "pass_criteria": "Bulk trash with confirmation"
    },
    {
        "user_input": "Permanently delete emails older than 2020",
        "expected_flow": "GmailFetchEmails → CRITICAL_WARNING → CONFIRMATION → GmailBatchDeleteMessages",
        "pass_criteria": "Shows critical warning and requires explicit confirmation"
    },
    {
        "user_input": "Delete draft draft_789",
        "expected_flow": "GmailGetDraft → SHOW_PREVIEW → CONFIRMATION → GmailDeleteDraft",
        "pass_criteria": "Shows draft preview before deletion"
    },
    {
        "user_input": "Remove this email",
        "expected_tool": "GmailMoveToTrash",
        "pass_criteria": "'Remove' defaults to safe trash"
    },
]
```

### 8.4 Label Management Test Cases

```python
TEST_CASES_LABELS = [
    {
        "user_input": "Label this email as Important",
        "expected_tool": "GmailAddLabel",
        "expected_params": {"message_id": "msg_123", "label_ids": ["IMPORTANT"]},
        "pass_criteria": "Adds IMPORTANT label to single message"
    },
    {
        "user_input": "Archive this conversation",
        "expected_tool": "GmailModifyThreadLabels",
        "expected_params": {"thread_id": "thread_456", "remove_label_ids": ["INBOX"]},
        "pass_criteria": "Removes INBOX from entire thread"
    },
    {
        "user_input": "Mark these 5 emails as read",
        "expected_tool": "GmailBatchModifyMessages",
        "expected_params": {"message_ids": [...], "remove_label_ids": ["UNREAD"]},
        "pass_criteria": "Bulk operation to remove UNREAD label"
    },
    {
        "user_input": "Star this email",
        "expected_tool": "GmailBatchModifyMessages",
        "expected_params": {"message_ids": ["msg_123"], "add_label_ids": ["STARRED"]},
        "pass_criteria": "Adds STARRED label"
    },
    {
        "user_input": "Create label 'ProjectX'",
        "expected_tool": "GmailCreateLabel",
        "expected_params": {"name": "ProjectX"},
        "pass_criteria": "Creates new custom label"
    },
]
```

### 8.5 Contact Search Test Cases

```python
TEST_CASES_CONTACTS = [
    {
        "user_input": "Find John Smith's email",
        "expected_tool": "GmailSearchPeople",
        "expected_params": {"query": "John Smith", "page_size": 10},
        "pass_criteria": "Searches contacts by name"
    },
    {
        "user_input": "Who is john@example.com?",
        "expected_tool": "GmailSearchPeople",
        "expected_params": {"query": "john@example.com", "page_size": 10},
        "pass_criteria": "Searches contacts by email"
    },
    {
        "user_input": "Show all my contacts",
        "expected_tool": "GmailGetContacts",
        "expected_params": {},
        "pass_criteria": "Lists all contacts"
    },
    {
        "user_input": "Get full details for this contact",
        "expected_workflow": "GmailSearchPeople → GmailGetPeople",
        "pass_criteria": "Two-step: search then get full profile"
    },
]
```

### 8.6 Ambiguity Resolution Test Cases

```python
TEST_CASES_AMBIGUITY = [
    {
        "user_input": "Delete emails from john@example.com",
        "expected_behavior": "Ask: 'Move to trash (recoverable) or permanently delete?'",
        "expected_default": "GmailMoveToTrash if user doesn't specify",
        "pass_criteria": "Clarifies trash vs permanent, defaults to safer option"
    },
    {
        "user_input": "Label this",
        "expected_behavior": "Ask: 'Label this message or entire conversation?'",
        "pass_criteria": "Clarifies scope (message vs thread)"
    },
    {
        "user_input": "Send email to John",
        "expected_behavior": "Search for 'John' → If multiple: Ask which John → Send",
        "pass_criteria": "Handles contact disambiguation"
    },
    {
        "user_input": "Email John about meeting",
        "expected_behavior": "Ask: 'Send immediately or create draft for review?'",
        "expected_default": "Draft mode (safer)",
        "pass_criteria": "Clarifies send mode, defaults to draft"
    },
]
```

### 8.7 Error Handling Test Cases

```python
TEST_CASES_ERRORS = [
    {
        "error_type": "404_NOT_FOUND",
        "scenario": "User tries to read email that doesn't exist",
        "expected_response": "'Email not found. It may have been deleted. Would you like to search again?'",
        "pass_criteria": "Provides helpful alternative"
    },
    {
        "error_type": "EMPTY_RESULTS",
        "scenario": "Search returns 0 emails",
        "expected_response": "'No emails found matching your criteria. Would you like to: 1) Try different search, 2) Check spam'",
        "pass_criteria": "Suggests alternative actions"
    },
    {
        "error_type": "INVALID_EMAIL",
        "scenario": "User provides malformed email address",
        "expected_response": "'Email address invalid. Did you mean {corrected}?'",
        "pass_criteria": "Attempts autocorrection"
    },
    {
        "error_type": "RATE_LIMIT",
        "scenario": "Gmail API rate limit exceeded",
        "expected_response": "'Rate limit exceeded. Retrying in {seconds} seconds...'",
        "pass_criteria": "Implements retry with backoff"
    },
    {
        "error_type": "AUTH_FAILURE",
        "scenario": "Gmail authentication expired",
        "expected_response": "'Authentication failed. Please reconnect your Gmail account at {link}'",
        "pass_criteria": "Provides clear reconnection instructions"
    },
]
```

### 8.8 Multi-Step Workflow Test Cases

```python
TEST_CASES_WORKFLOWS = [
    {
        "workflow_name": "Draft_Review_Send",
        "user_inputs": [
            "Draft email to john@example.com",
            "Send it"
        ],
        "expected_steps": [
            "GmailCreateDraft",
            "Present draft to user",
            "GmailSendDraft"
        ],
        "pass_criteria": "Completes full draft→review→send flow"
    },
    {
        "workflow_name": "Search_Organize_Report",
        "user_inputs": [
            "Archive all emails from newsletters",
            "yes"  # Confirmation
        ],
        "expected_steps": [
            "GmailFetchEmails(query='from:*newsletter*')",
            "Present count for confirmation",
            "GmailBatchModifyMessages(remove_label_ids=['INBOX'])",
            "Report success"
        ],
        "pass_criteria": "Completes bulk organize workflow with confirmation"
    },
    {
        "workflow_name": "Contact_Disambiguate_Email",
        "user_inputs": [
            "Send email to John",
            "John Smith"  # Disambiguation
        ],
        "expected_steps": [
            "GmailSearchPeople(query='John')",
            "Present multiple Johns",
            "User selects John Smith",
            "GmailSendEmail(to='john.smith@example.com')"
        ],
        "pass_criteria": "Handles contact disambiguation correctly"
    },
]
```

---

## 9. Implementation Recommendations

### 9.1 Routing Engine Structure

```python
class GmailRoutingEngine:
    """
    CEO Agent routing engine for Gmail tool orchestration.
    """

    def __init__(self):
        self.intent_patterns = self._load_intent_patterns()
        self.safety_rules = self._load_safety_rules()
        self.workflow_registry = self._load_workflows()

    def route(self, user_input: str, context: dict) -> dict:
        """
        Main routing function.

        Args:
            user_input: Raw user query
            context: Current conversation context (message_ids, thread_ids, etc.)

        Returns:
            Routing decision with tool, params, and workflow steps
        """
        # 1. Detect intent
        intent = self.detect_intent(user_input)

        # 2. Check for ambiguity
        if intent.is_ambiguous:
            return self.request_clarification(intent)

        # 3. Apply safety rules
        if self.requires_confirmation(intent):
            return self.build_confirmation_flow(intent)

        # 4. Route to tool or workflow
        if intent.is_multi_step:
            return self.build_workflow(intent, context)
        else:
            return self.build_single_tool_call(intent, context)

    def detect_intent(self, user_input: str) -> Intent:
        """Detect user intent using pattern matching."""
        pass

    def requires_confirmation(self, intent: Intent) -> bool:
        """Check if intent requires safety confirmation."""
        if intent.operation == "permanent_delete":
            return True
        if intent.operation == "bulk" and intent.count > 10:
            return True
        return False

    def build_workflow(self, intent: Intent, context: dict) -> Workflow:
        """Build multi-step workflow for complex intents."""
        pass
```

### 9.2 Intent Detection Implementation

```python
class IntentDetector:
    """
    Detects user intent from natural language input.
    """

    def __init__(self):
        self.patterns = {
            "fetch": [
                r"show.*emails",
                r"list.*emails",
                r"what.*emails",
                r"find.*emails",
                r"search.*emails",
            ],
            "send": [
                r"send email to (.+)",
                r"email (.+) about (.+)",
                r"send message to (.+)",
            ],
            "delete": [
                r"delete.*email",
                r"permanently delete",
                r"trash.*this",
                r"remove.*email",
            ],
            # ... more patterns
        }

    def detect(self, user_input: str) -> Intent:
        """
        Detect intent from user input.

        Returns:
            Intent object with:
            - category: fetch/send/delete/organize/contact
            - operation: specific operation within category
            - entities: extracted entities (email, name, date, etc.)
            - confidence: 0-1 confidence score
            - is_ambiguous: whether intent needs clarification
        """
        # Pattern matching logic
        # Entity extraction logic
        # Confidence scoring logic
        pass
```

### 9.3 Safety Confirmation System

```python
class SafetyConfirmationSystem:
    """
    Manages safety confirmations for destructive operations.
    """

    DANGEROUS_OPERATIONS = [
        "permanent_delete",
        "bulk_delete",
        "label_delete",
    ]

    def requires_confirmation(self, operation: str, count: int = 1) -> bool:
        """Check if operation requires confirmation."""
        if operation in self.DANGEROUS_OPERATIONS:
            return True
        if count > 10:  # Bulk operations
            return True
        return False

    def build_confirmation_prompt(self, operation: str, details: dict) -> str:
        """Build confirmation prompt for user."""
        if operation == "permanent_delete":
            return f"""
⚠️ WARNING: PERMANENT DELETION

This will PERMANENTLY delete {details['count']} email(s).
- CANNOT be recovered
- NOT moved to trash
- Deletion is IRREVERSIBLE

Messages to be deleted:
{self._format_email_list(details['emails'])}

Type 'CONFIRM PERMANENT DELETE' to proceed, or 'CANCEL' to abort.
"""
        elif operation == "bulk_delete":
            return f"""
I found {details['count']} emails matching your criteria.

Would you like to:
- Move to trash (recoverable for 30 days) ← RECOMMENDED
- Permanently delete (CANNOT recover)
- Cancel

Which would you prefer?
"""
        # ... more confirmation templates

    def validate_confirmation(self, user_response: str, operation: str) -> bool:
        """Validate user confirmation response."""
        if operation == "permanent_delete":
            return user_response.strip().upper() == "CONFIRM PERMANENT DELETE"
        else:
            return user_response.strip().lower() in ["yes", "confirm", "proceed"]
```

### 9.4 Workflow Orchestrator

```python
class WorkflowOrchestrator:
    """
    Orchestrates multi-step workflows.
    """

    def __init__(self):
        self.workflows = {
            "draft_review_send": DraftReviewSendWorkflow(),
            "search_organize_report": SearchOrganizeReportWorkflow(),
            "contact_disambiguate_email": ContactDisambiguateEmailWorkflow(),
            "bulk_delete_safe": BulkDeleteSafeWorkflow(),
        }

    def execute_workflow(self, workflow_name: str, params: dict) -> WorkflowResult:
        """Execute named workflow with parameters."""
        workflow = self.workflows.get(workflow_name)
        if not workflow:
            raise ValueError(f"Unknown workflow: {workflow_name}")

        return workflow.execute(params)

class DraftReviewSendWorkflow:
    """Draft → Review → Send workflow."""

    async def execute(self, params: dict) -> WorkflowResult:
        # Step 1: Create draft
        draft = await self.create_draft(params)

        # Step 2: Present for review
        approval = await self.present_for_review(draft)

        # Step 3: Handle approval
        if approval.status == "send":
            result = await self.send_draft(draft.id)
            return WorkflowResult(success=True, message_id=result.message_id)
        elif approval.status == "revise":
            revised_draft = await self.revise_draft(draft, approval.changes)
            return await self.execute({"draft": revised_draft})  # Recursive
        else:  # cancel
            return WorkflowResult(success=False, draft_saved=True)
```

---

## 10. Performance Considerations

### 10.1 Caching Strategy

```python
CACHING_STRATEGY = {
    "label_list": {
        "ttl": 3600,  # 1 hour
        "reason": "Labels change infrequently"
    },
    "contact_search": {
        "ttl": 1800,  # 30 minutes
        "reason": "Contacts change occasionally"
    },
    "draft_list": {
        "ttl": 60,  # 1 minute
        "reason": "Drafts change frequently"
    },
    "email_fetch": {
        "ttl": 30,  # 30 seconds
        "reason": "New emails arrive constantly"
    }
}
```

### 10.2 Rate Limiting

```python
RATE_LIMITS = {
    "gmail_api": {
        "requests_per_second": 25,
        "requests_per_day": 1000000,
        "quota_user": "user_email"
    },
    "bulk_operations": {
        "max_batch_size": 100,
        "delay_between_batches": 1.0  # seconds
    }
}
```

### 10.3 Optimization Patterns

- Use `GmailFetchEmails` with specific queries instead of fetching all and filtering
- Batch operations when possible (GmailBatchModifyMessages vs multiple GmailAddLabel calls)
- Cache label IDs to avoid repeated GmailListLabels calls
- Use pagination for large result sets
- Implement exponential backoff for retries

---

## 11. Monitoring & Logging

### 11.1 Metrics to Track

```python
METRICS = {
    "routing_accuracy": "% of intents correctly routed",
    "confirmation_rate": "% of operations requiring confirmation",
    "workflow_completion_rate": "% of multi-step workflows completed",
    "error_rate": "% of operations resulting in errors",
    "average_response_time": "ms from user input to tool execution",
    "clarification_rate": "% of ambiguous intents requiring clarification",
    "safety_intervention_rate": "% of dangerous ops prevented by safety rules"
}
```

### 11.2 Logging Strategy

```python
LOG_EVENTS = {
    "intent_detected": {
        "level": "INFO",
        "fields": ["user_input", "detected_intent", "confidence", "entities"]
    },
    "tool_routed": {
        "level": "INFO",
        "fields": ["tool_name", "parameters", "workflow_id"]
    },
    "confirmation_required": {
        "level": "WARNING",
        "fields": ["operation", "reason", "count", "user_response"]
    },
    "safety_intervention": {
        "level": "CRITICAL",
        "fields": ["operation", "prevented_action", "user_input"]
    },
    "error_occurred": {
        "level": "ERROR",
        "fields": ["error_type", "tool_name", "error_message", "stack_trace"]
    }
}
```

---

## 12. Summary & Next Steps

### 12.1 Architecture Summary

This routing architecture provides:

1. **Comprehensive Tool Coverage**: All 25 Gmail tools organized into 7 functional categories
2. **Intelligent Intent Detection**: 50+ intent patterns with fuzzy matching and disambiguation
3. **Safety-First Design**: Mandatory confirmations for destructive operations with clear warnings
4. **Multi-Step Workflows**: Pre-built workflows for common complex operations
5. **Robust Error Handling**: Graceful fallbacks for all error scenarios
6. **Clear Decision Trees**: Text-based decision diagrams for each operation category
7. **Extensive Test Cases**: 50+ test cases covering routing, safety, ambiguity, and errors

### 12.2 Implementation Checklist

- [ ] Implement IntentDetector with pattern matching
- [ ] Build GmailRoutingEngine with routing logic
- [ ] Create SafetyConfirmationSystem with confirmation flows
- [ ] Develop WorkflowOrchestrator with multi-step workflows
- [ ] Update CEO instructions.md with routing guide
- [ ] Write unit tests for routing engine
- [ ] Write integration tests for workflows
- [ ] Implement caching layer for performance
- [ ] Add rate limiting and retry logic
- [ ] Set up monitoring and logging
- [ ] Create routing analytics dashboard
- [ ] Document edge cases and limitations

### 12.3 Priority Implementation Order

**Phase 1: Core Routing (Week 1)**
1. Intent detection engine
2. Basic routing for fetch/send/delete
3. Safety confirmation system
4. CEO instructions update

**Phase 2: Workflows (Week 2)**
5. Draft→Review→Send workflow
6. Search→Organize→Report workflow
7. Bulk delete safety workflow

**Phase 3: Polish (Week 3)**
8. Error handling and fallbacks
9. Ambiguity resolution
10. Performance optimization (caching, rate limiting)

**Phase 4: Validation (Week 4)**
11. Comprehensive testing (all test cases)
12. User acceptance testing
13. Monitoring and analytics setup

---

## Appendix A: Quick Reference

### Tool Selection Cheat Sheet

| User Says | Use This Tool | Notes |
|-----------|---------------|-------|
| "Show emails" | GmailFetchEmails | Default query="" |
| "Unread emails" | GmailFetchEmails | query="is:unread" |
| "Send email to X" | GmailSendEmail | Immediate send |
| "Draft email to X" | GmailCreateDraft | Needs approval |
| "Delete email" | GmailMoveToTrash | SAFE default |
| "Permanently delete" | GmailDeleteMessage | REQUIRES CONFIRMATION |
| "Archive this" | GmailBatchModifyMessages | remove_label_ids=["INBOX"] |
| "Star this" | GmailBatchModifyMessages | add_label_ids=["STARRED"] |
| "Find John's email" | GmailSearchPeople | Search contacts |
| "Label as Important" | GmailAddLabel | Single message |
| "Archive conversation" | GmailModifyThreadLabels | Entire thread |

### Safety Rules Cheat Sheet

| Operation | Confirmation Required? | Default Behavior |
|-----------|----------------------|------------------|
| Delete (no "permanently") | NO | GmailMoveToTrash |
| Permanent delete | YES (explicit) | Abort if not confirmed |
| Bulk operation (>10) | YES | Show count, ask confirmation |
| Draft deletion | YES (show preview) | Show draft before deleting |
| Label deletion | YES (if label has messages) | Show impact before deleting |
| Send email | NO (if "send" keyword) | Immediate send |
| Draft email | NO | Create draft, show for approval |

---

**END OF ROUTING ARCHITECTURE DOCUMENT**

Generated by: Backend Architect Agent
For: Master Coordination Agent → CEO Agent Integration
Status: READY FOR VALIDATION BY SERENA-VALIDATOR
