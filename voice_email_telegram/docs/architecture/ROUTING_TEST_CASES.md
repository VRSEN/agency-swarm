# Gmail Routing Test Cases
**Version**: 1.0
**Date**: 2025-11-01
**Purpose**: Comprehensive test cases to validate CEO Gmail routing architecture

---

## Test Suite Overview

- **Total Test Cases**: 75
- **Categories**: 8
- **Coverage**: Intent detection, routing, safety, workflows, errors
- **Pass Criteria**: 100% of critical safety tests, 95% of routing tests

---

## Test Category 1: Fetch/Read Routing (12 tests)

### TEST-FETCH-001: Basic Email Fetch
```yaml
test_id: FETCH-001
name: Basic email fetch with no filters
user_input: "Show me my emails"
expected_intent: fetch_emails
expected_tool: GmailFetchEmails
expected_params:
  query: ""
  max_results: 10
pass_criteria: Tool called with correct params
priority: HIGH
```

### TEST-FETCH-002: Unread Filter
```yaml
test_id: FETCH-002
name: Fetch unread emails only
user_input: "What are my unread emails?"
expected_intent: fetch_unread
expected_tool: GmailFetchEmails
expected_params:
  query: "is:unread"
  max_results: 10
pass_criteria: Unread filter correctly applied
priority: HIGH
```

### TEST-FETCH-003: Sender Filter
```yaml
test_id: FETCH-003
name: Fetch emails from specific sender
user_input: "Show emails from john@example.com"
expected_intent: fetch_from_sender
expected_tool: GmailFetchEmails
expected_params:
  query: "from:john@example.com"
  max_results: 10
extracted_entities:
  sender_email: "john@example.com"
pass_criteria: Email extracted and query built correctly
priority: HIGH
```

### TEST-FETCH-004: Subject Search
```yaml
test_id: FETCH-004
name: Search emails by subject keyword
user_input: "Find emails about meeting"
expected_intent: fetch_by_subject
expected_tool: GmailFetchEmails
expected_params:
  query: "subject:meeting"
  max_results: 10
extracted_entities:
  subject_keyword: "meeting"
pass_criteria: Subject filter correctly constructed
priority: MEDIUM
```

### TEST-FETCH-005: Complex Query
```yaml
test_id: FETCH-005
name: Multiple filters combined
user_input: "Show unread emails from john@example.com about project"
expected_intent: fetch_complex
expected_tool: GmailFetchEmails
expected_params:
  query: "from:john@example.com subject:project is:unread"
  max_results: 10
extracted_entities:
  sender_email: "john@example.com"
  subject_keyword: "project"
  status: "unread"
pass_criteria: All filters combined with AND logic
priority: HIGH
```

### TEST-FETCH-006: Date Range
```yaml
test_id: FETCH-006
name: Fetch emails from specific date range
user_input: "Show emails from last week"
expected_intent: fetch_by_date
expected_tool: GmailFetchEmails
expected_params:
  query: "newer_than:7d"
  max_results: 10
extracted_entities:
  date_range: "7d"
pass_criteria: Date correctly parsed to Gmail query format
priority: MEDIUM
```

### TEST-FETCH-007: Attachment Filter
```yaml
test_id: FETCH-007
name: Fetch emails with attachments
user_input: "Show emails with attachments"
expected_intent: fetch_with_attachments
expected_tool: GmailFetchEmails
expected_params:
  query: "has:attachment"
  max_results: 10
pass_criteria: Attachment filter correctly applied
priority: MEDIUM
```

### TEST-FETCH-008: Starred Emails
```yaml
test_id: FETCH-008
name: Fetch starred emails
user_input: "What are my starred emails?"
expected_intent: fetch_starred
expected_tool: GmailFetchEmails
expected_params:
  query: "is:starred"
  max_results: 10
pass_criteria: Starred filter correctly applied
priority: MEDIUM
```

### TEST-FETCH-009: Custom Result Count
```yaml
test_id: FETCH-009
name: Fetch specific number of emails
user_input: "Show me my last 20 emails"
expected_intent: fetch_with_count
expected_tool: GmailFetchEmails
expected_params:
  query: ""
  max_results: 20
extracted_entities:
  count: 20
pass_criteria: Custom max_results correctly set
priority: LOW
```

### TEST-FETCH-010: Read Single Message
```yaml
test_id: FETCH-010
name: Read specific message by workflow
user_input: "Read the email from Sarah"
expected_intent: read_from_sender
expected_workflow:
  - tool: GmailFetchEmails
    params: {query: "from:sarah", max_results: 1}
  - tool: GmailGetMessage
    params: {message_id: "{extracted_from_fetch}"}
pass_criteria: Two-step workflow executed in order
priority: HIGH
```

### TEST-FETCH-011: Read Thread
```yaml
test_id: FETCH-011
name: Read entire conversation
user_input: "Show me this entire conversation"
expected_intent: read_thread
expected_tool: GmailFetchMessageByThreadId
expected_params:
  thread_id: "{from_context}"
context_required:
  - thread_id
pass_criteria: Thread fetched using context thread_id
priority: MEDIUM
```

### TEST-FETCH-012: Get Attachment
```yaml
test_id: FETCH-012
name: Download attachment from email
user_input: "Get the PDF from this email"
expected_intent: get_attachment
expected_workflow:
  - tool: GmailGetMessage
    params: {message_id: "{from_context}"}
  - extract: attachment_id (filter by type=pdf)
  - tool: GmailGetAttachment
    params: {message_id: "{from_context}", attachment_id: "{extracted}"}
context_required:
  - message_id
pass_criteria: Attachment extracted and downloaded
priority: MEDIUM
```

---

## Test Category 2: Send/Draft Routing (10 tests)

### TEST-SEND-001: Direct Send
```yaml
test_id: SEND-001
name: Send email immediately
user_input: "Send email to john@example.com about the meeting"
expected_intent: send_email_immediate
expected_tool: GmailSendEmail
expected_params:
  to: "john@example.com"
  subject: "Meeting"  # or extracted from voice intent
  body: "{composed_from_voice}"
extracted_entities:
  recipient_email: "john@example.com"
  topic: "meeting"
pass_criteria: Email sent immediately without draft
priority: HIGH
```

### TEST-SEND-002: Draft Workflow
```yaml
test_id: SEND-002
name: Create draft for review
user_input: "Draft an email to sarah@company.com"
expected_intent: create_draft_workflow
expected_workflow:
  - tool: GmailCreateDraft
    params: {to: "sarah@company.com", subject: "...", body: "..."}
  - action: present_to_user
  - wait: user_approval
  - tool: GmailSendDraft (if approved)
    params: {draft_id: "{created_draft_id}"}
pass_criteria: Draft created and approval workflow initiated
priority: HIGH
```

### TEST-SEND-003: Send Existing Draft
```yaml
test_id: SEND-003
name: Send draft by ID
user_input: "Send draft draft_456"
expected_intent: send_draft_by_id
expected_tool: GmailSendDraft
expected_params:
  draft_id: "draft_456"
extracted_entities:
  draft_id: "draft_456"
pass_criteria: Draft sent directly without approval
priority: MEDIUM
```

### TEST-SEND-004: Send with CC
```yaml
test_id: SEND-004
name: Send email with CC
user_input: "Send email to john@example.com and CC sarah@example.com"
expected_intent: send_with_cc
expected_tool: GmailSendEmail
expected_params:
  to: "john@example.com"
  cc: "sarah@example.com"
  subject: "..."
  body: "..."
extracted_entities:
  recipient_email: "john@example.com"
  cc_email: "sarah@example.com"
pass_criteria: Both To and CC correctly set
priority: MEDIUM
```

### TEST-SEND-005: Draft Revision
```yaml
test_id: SEND-005
name: Revise draft before sending
user_input_sequence:
  - "Draft email to john@example.com"
  - "Make the subject more specific"
expected_intent: revise_draft
expected_workflow:
  - tool: GmailCreateDraft (initial)
  - tool: ReviseEmailDraft
    params: {draft_id: "{created}", changes: "make subject more specific"}
  - action: present_revised
  - wait: user_approval
pass_criteria: Draft revised and presented again
priority: HIGH
```

### TEST-SEND-006: Cancel Draft
```yaml
test_id: SEND-006
name: Cancel draft creation
user_input_sequence:
  - "Draft email to sarah@example.com"
  - "Cancel, I changed my mind"
expected_intent: cancel_draft
expected_workflow:
  - tool: GmailCreateDraft (initial)
  - action: cancel_workflow
  - ask: "Would you like to keep the draft or delete it?"
  - if_delete: GmailDeleteDraft
pass_criteria: Draft workflow cancelled, user given delete option
priority: LOW
```

### TEST-SEND-007: Send to Contact by Name
```yaml
test_id: SEND-007
name: Send to contact found by name
user_input: "Email John Smith about the project"
expected_intent: send_to_contact
expected_workflow:
  - tool: GmailSearchPeople
    params: {query: "John Smith"}
  - if_multiple: disambiguation
  - extract: email_address
  - tool: GmailSendEmail
    params: {to: "{extracted_email}", subject: "Project", body: "..."}
pass_criteria: Contact found and email sent
priority: MEDIUM
```

### TEST-SEND-008: Compose Keyword (Draft Mode)
```yaml
test_id: SEND-008
name: "Compose" triggers draft workflow
user_input: "Compose message to team@company.com"
expected_intent: compose_draft
expected_workflow:
  - tool: GmailCreateDraft
  - action: present_for_review
  - wait: approval
pass_criteria: "Compose" triggers draft mode, not immediate send
priority: MEDIUM
```

### TEST-SEND-009: Ambiguous Send Mode
```yaml
test_id: SEND-009
name: Ambiguous send intent defaults to draft
user_input: "Email Sarah about vacation"
expected_intent: send_ambiguous
expected_behavior:
  clarification: "Would you like to: 1) Create draft for review, 2) Send immediately"
  default_if_no_response: create_draft
pass_criteria: Asks for clarification, defaults to safer draft mode
priority: MEDIUM
```

### TEST-SEND-010: Send Latest Draft
```yaml
test_id: SEND-010
name: Send most recent draft
user_input: "Send the draft I just created"
expected_intent: send_latest_draft
expected_workflow:
  - tool: GmailListDrafts (max_results=1, sort=newest)
  - extract: draft_id
  - tool: GmailSendDraft
    params: {draft_id: "{extracted}"}
pass_criteria: Latest draft identified and sent
priority: LOW
```

---

## Test Category 3: Delete Safety Tests (15 tests) ⚠️ CRITICAL

### TEST-DELETE-001: Safe Delete (Default)
```yaml
test_id: DELETE-001
name: "Delete" defaults to trash
user_input: "Delete this email"
expected_intent: delete_safe
expected_tool: GmailMoveToTrash
expected_params:
  message_id: "{from_context}"
safety_rule: MUST default to trash, NOT permanent delete
pass_criteria: GmailMoveToTrash called, NOT GmailDeleteMessage
priority: CRITICAL
```

### TEST-DELETE-002: Permanent Delete Requires Confirmation
```yaml
test_id: DELETE-002
name: Permanent delete requires explicit confirmation
user_input: "Permanently delete this email"
expected_intent: delete_permanent
expected_workflow:
  - action: HALT_EXECUTION
  - action: present_warning
    warning_text: "⚠️ WARNING: PERMANENT DELETION..."
  - wait: user_confirmation
    required_text: "CONFIRM PERMANENT DELETE"
  - if_confirmed: GmailDeleteMessage
  - if_not_confirmed: ABORT
safety_rule: NEVER permanent delete without confirmation
pass_criteria: Confirmation required and validated
priority: CRITICAL
```

### TEST-DELETE-003: Confirmation Text Validation
```yaml
test_id: DELETE-003
name: Reject incorrect confirmation text
user_input_sequence:
  - "Permanently delete this email"
  - "yes"  # Incorrect, should be "CONFIRM PERMANENT DELETE"
expected_behavior:
  - present_warning
  - wait_for_confirmation
  - received: "yes"
  - reject: "Invalid confirmation. Type 'CONFIRM PERMANENT DELETE' or 'CANCEL'"
  - wait_again
expected_outcome: Operation NOT executed with "yes"
safety_rule: Require exact confirmation phrase
pass_criteria: Operation aborted due to incorrect confirmation
priority: CRITICAL
```

### TEST-DELETE-004: Cancel Permanent Delete
```yaml
test_id: DELETE-004
name: User can cancel permanent deletion
user_input_sequence:
  - "Permanently delete this email"
  - "CANCEL"
expected_workflow:
  - present_warning
  - wait_for_confirmation
  - received: "CANCEL"
  - action: ABORT
  - suggest: "Would you like to move to trash instead?"
expected_outcome: No deletion occurred
pass_criteria: Operation cancelled successfully
priority: CRITICAL
```

### TEST-DELETE-005: Bulk Delete Confirmation
```yaml
test_id: DELETE-005
name: Bulk delete requires confirmation for >10 items
user_input: "Delete all emails from spam@example.com"
expected_workflow:
  - tool: GmailFetchEmails
    params: {query: "from:spam@example.com"}
  - result: 47 emails found
  - action: HALT (count > 10 threshold)
  - present: "Found 47 emails. Move to trash (recoverable) or permanently delete?"
  - wait: user_choice
  - if_trash: loop GmailMoveToTrash
  - if_permanent: require_confirmation → GmailBatchDeleteMessages
safety_rule: Bulk operations require confirmation
pass_criteria: Confirmation presented for 47 items
priority: CRITICAL
```

### TEST-DELETE-006: Permanent Bulk with Count Display
```yaml
test_id: DELETE-006
name: Show count before permanent bulk delete
user_input_sequence:
  - "Permanently delete emails older than 2020"
  - "CONFIRM PERMANENT DELETE"
expected_workflow:
  - tool: GmailFetchEmails
    params: {query: "before:2020/01/01"}
  - result: 234 emails
  - present: "⚠️ Will PERMANENTLY delete 234 emails. CANNOT recover. Confirm?"
  - received: "CONFIRM PERMANENT DELETE"
  - action: split into batches (max 100 per batch)
  - tool: GmailBatchDeleteMessages (batch 1: 100 items)
  - tool: GmailBatchDeleteMessages (batch 2: 100 items)
  - tool: GmailBatchDeleteMessages (batch 3: 34 items)
  - report: "⚠️ 234 emails PERMANENTLY deleted"
safety_rule: Show exact count and batch properly
pass_criteria: Count displayed, batches split correctly
priority: CRITICAL
```

### TEST-DELETE-007: Draft Delete Preview
```yaml
test_id: DELETE-007
name: Show draft preview before deletion
user_input: "Delete draft draft_789"
expected_workflow:
  - tool: GmailGetDraft
    params: {draft_id: "draft_789"}
  - action: present_preview
    show: {to, subject, body_snippet}
  - ask: "Delete this draft? (yes/no)"
  - wait: user_response
  - if_yes: GmailDeleteDraft
  - if_no: ABORT
safety_rule: Show what will be deleted
pass_criteria: Draft preview shown before deletion
priority: MEDIUM
```

### TEST-DELETE-008: "Remove" Defaults to Trash
```yaml
test_id: DELETE-008
name: "Remove" synonym defaults to safe delete
user_input: "Remove this email"
expected_intent: delete_safe
expected_tool: GmailMoveToTrash
safety_rule: All delete synonyms default to trash
pass_criteria: GmailMoveToTrash called, NOT permanent delete
priority: HIGH
```

### TEST-DELETE-009: "Trash" Keyword
```yaml
test_id: DELETE-009
name: Explicit "trash" uses safe delete
user_input: "Trash this email"
expected_intent: delete_to_trash
expected_tool: GmailMoveToTrash
pass_criteria: Trash tool called correctly
priority: MEDIUM
```

### TEST-DELETE-010: Permanent Delete Single Message
```yaml
test_id: DELETE-010
name: Permanent delete single message (confirmed)
user_input_sequence:
  - "Permanently delete message msg_123"
  - "CONFIRM PERMANENT DELETE"
expected_workflow:
  - present_warning
  - wait_confirmation
  - received: correct confirmation
  - tool: GmailDeleteMessage
    params: {message_id: "msg_123"}
  - report: "⚠️ Message PERMANENTLY deleted. Cannot be recovered."
pass_criteria: Single permanent delete executed after confirmation
priority: HIGH
```

### TEST-DELETE-011: "Delete Forever" Synonym
```yaml
test_id: DELETE-011
name: "Delete forever" triggers permanent delete flow
user_input: "Delete this email forever"
expected_intent: delete_permanent
expected_workflow: Same as TEST-DELETE-002
safety_rule: "Forever" keyword triggers permanent delete confirmation
pass_criteria: Confirmation flow triggered
priority: HIGH
```

### TEST-DELETE-012: Batch Size Limit Enforcement
```yaml
test_id: DELETE-012
name: Batch delete respects 100-item limit
user_input_sequence:
  - "Permanently delete all spam emails"  # Assume 250 found
  - "CONFIRM PERMANENT DELETE"
expected_workflow:
  - fetch: 250 emails
  - confirm
  - batch_1: GmailBatchDeleteMessages(message_ids[0:100])
  - batch_2: GmailBatchDeleteMessages(message_ids[100:200])
  - batch_3: GmailBatchDeleteMessages(message_ids[200:250])
safety_rule: Never exceed 100 items per batch
pass_criteria: Split into 3 batches correctly
priority: HIGH
```

### TEST-DELETE-013: Empty Result Safety
```yaml
test_id: DELETE-013
name: Handle delete request with no matches
user_input: "Delete all emails from nonexistent@example.com"
expected_workflow:
  - tool: GmailFetchEmails
    params: {query: "from:nonexistent@example.com"}
  - result: 0 emails
  - action: ABORT
  - report: "No emails found matching criteria. Nothing to delete."
safety_rule: Don't execute empty operations
pass_criteria: Reports no matches, doesn't error
priority: LOW
```

### TEST-DELETE-014: Delete from Trash (Already Trashed)
```yaml
test_id: DELETE-014
name: Handle delete of already-trashed email
user_input: "Delete this email"
context:
  message_id: "msg_123"
  labels: ["TRASH"]
expected_workflow:
  - tool: GmailMoveToTrash (idempotent)
  - result: success (email already in trash)
  - report: "Email moved to trash (already in trash folder)"
pass_criteria: Handles already-trashed gracefully
priority: LOW
```

### TEST-DELETE-015: Timeout on Confirmation
```yaml
test_id: DELETE-015
name: Timeout if user doesn't confirm within reasonable time
user_input_sequence:
  - "Permanently delete this email"
  - [wait 60 seconds with no response]
expected_workflow:
  - present_warning
  - wait_confirmation (timeout=60s)
  - timeout_reached
  - action: ABORT
  - report: "Permanent deletion cancelled due to no confirmation. Email NOT deleted."
safety_rule: Auto-abort if no confirmation
pass_criteria: Operation cancelled after timeout
priority: MEDIUM
```

---

## Test Category 4: Organize Operations (10 tests)

### TEST-ORGANIZE-001: Mark as Read
```yaml
test_id: ORGANIZE-001
name: Mark single email as read
user_input: "Mark this as read"
expected_tool: GmailBatchModifyMessages
expected_params:
  message_ids: ["{from_context}"]
  remove_label_ids: ["UNREAD"]
pass_criteria: UNREAD label removed
priority: HIGH
```

### TEST-ORGANIZE-002: Star Email
```yaml
test_id: ORGANIZE-002
name: Star single email
user_input: "Star this email"
expected_tool: GmailBatchModifyMessages
expected_params:
  message_ids: ["{from_context}"]
  add_label_ids: ["STARRED"]
pass_criteria: STARRED label added
priority: HIGH
```

### TEST-ORGANIZE-003: Archive Single
```yaml
test_id: ORGANIZE-003
name: Archive single email
user_input: "Archive this email"
expected_tool: GmailBatchModifyMessages
expected_params:
  message_ids: ["{from_context}"]
  remove_label_ids: ["INBOX"]
pass_criteria: INBOX label removed
priority: HIGH
```

### TEST-ORGANIZE-004: Archive Thread
```yaml
test_id: ORGANIZE-004
name: Archive entire conversation
user_input: "Archive this conversation"
expected_tool: GmailModifyThreadLabels
expected_params:
  thread_id: "{from_context}"
  remove_label_ids: ["INBOX"]
pass_criteria: Thread tool used, not message tool
priority: HIGH
```

### TEST-ORGANIZE-005: Add Custom Label
```yaml
test_id: ORGANIZE-005
name: Add custom label to email
user_input: "Label this as ProjectX"
expected_workflow:
  - tool: GmailListLabels
  - search: "ProjectX"
  - if_found: label_id = "{found_id}"
  - if_not_found: GmailCreateLabel(name="ProjectX") → label_id
  - tool: GmailAddLabel
    params: {message_id: "{context}", label_ids: [label_id]}
pass_criteria: Label added (created if necessary)
priority: MEDIUM
```

### TEST-ORGANIZE-006: Bulk Mark Read
```yaml
test_id: ORGANIZE-006
name: Mark multiple emails as read
user_input: "Mark all these as read"
context:
  message_ids: ["msg_1", "msg_2", "msg_3"]
expected_tool: GmailBatchModifyMessages
expected_params:
  message_ids: ["msg_1", "msg_2", "msg_3"]
  remove_label_ids: ["UNREAD"]
pass_criteria: Batch operation on multiple messages
priority: HIGH
```

### TEST-ORGANIZE-007: Star Conversation
```yaml
test_id: ORGANIZE-007
name: Star entire thread
user_input: "Star this entire conversation"
expected_tool: GmailModifyThreadLabels
expected_params:
  thread_id: "{from_context}"
  add_label_ids: ["STARRED"]
pass_criteria: Thread operation, not individual messages
priority: MEDIUM
```

### TEST-ORGANIZE-008: Create Label
```yaml
test_id: ORGANIZE-008
name: Create new custom label
user_input: "Create label 'Urgent'"
expected_tool: GmailCreateLabel
expected_params:
  name: "Urgent"
pass_criteria: Label created successfully
priority: LOW
```

### TEST-ORGANIZE-009: Mark Unread
```yaml
test_id: ORGANIZE-009
name: Mark email as unread
user_input: "Mark this as unread"
expected_tool: GmailBatchModifyMessages
expected_params:
  message_ids: ["{from_context}"]
  add_label_ids: ["UNREAD"]
pass_criteria: UNREAD label added
priority: MEDIUM
```

### TEST-ORGANIZE-010: Unstar
```yaml
test_id: ORGANIZE-010
name: Remove star from email
user_input: "Unstar this email"
expected_tool: GmailBatchModifyMessages
expected_params:
  message_ids: ["{from_context}"]
  remove_label_ids: ["STARRED"]
pass_criteria: STARRED label removed
priority: LOW
```

---

## Test Category 5: Contact Search (6 tests)

### TEST-CONTACT-001: Search by Name
```yaml
test_id: CONTACT-001
name: Find contact by name
user_input: "Find John Smith's email"
expected_tool: GmailSearchPeople
expected_params:
  query: "John Smith"
  page_size: 10
pass_criteria: Contact search executed
priority: HIGH
```

### TEST-CONTACT-002: Search by Email
```yaml
test_id: CONTACT-002
name: Find contact by email address
user_input: "Who is john@example.com?"
expected_tool: GmailSearchPeople
expected_params:
  query: "john@example.com"
  page_size: 10
pass_criteria: Email used as search query
priority: MEDIUM
```

### TEST-CONTACT-003: Get Full Details
```yaml
test_id: CONTACT-003
name: Get complete contact profile
user_input: "Get full details for John Smith"
expected_workflow:
  - tool: GmailSearchPeople(query="John Smith")
  - extract: resource_name
  - tool: GmailGetPeople(resource_name="{extracted}")
pass_criteria: Two-step workflow for full details
priority: MEDIUM
```

### TEST-CONTACT-004: List All Contacts
```yaml
test_id: CONTACT-004
name: List all Gmail contacts
user_input: "Show all my contacts"
expected_tool: GmailGetContacts
expected_params: {}
pass_criteria: All contacts retrieved
priority: LOW
```

### TEST-CONTACT-005: Disambiguate Multiple Results
```yaml
test_id: CONTACT-005
name: Handle multiple contact matches
user_input: "Find John's email"
expected_workflow:
  - tool: GmailSearchPeople(query="John")
  - result: 3 Johns found
  - action: present_options
    options:
      - "John Smith (john.smith@company.com)"
      - "John Doe (john.doe@company.com)"
      - "John Johnson (jjohnson@partner.com)"
  - wait: user_selection
pass_criteria: Disambiguation presented
priority: HIGH
```

### TEST-CONTACT-006: No Results Found
```yaml
test_id: CONTACT-006
name: Handle contact not found
user_input: "Find xyz@nonexistent.com"
expected_workflow:
  - tool: GmailSearchPeople(query="xyz@nonexistent.com")
  - result: 0 contacts
  - action: report_not_found
  - suggest: "Try a different name or email, or add as new contact"
pass_criteria: Helpful suggestion provided
priority: MEDIUM
```

---

## Test Category 6: Error Handling (10 tests)

### TEST-ERROR-001: Authentication Failure
```yaml
test_id: ERROR-001
name: Handle 401 auth error
scenario: Gmail token expired
mock_api_response:
  status: 401
  error: "Unauthorized"
expected_behavior:
  - detect: authentication_error
  - action: report_to_user
    message: "Gmail authentication failed. Please reconnect your Gmail account."
  - provide: reconnection_link
pass_criteria: Clear error message with action steps
priority: HIGH
```

### TEST-ERROR-002: Rate Limit Exceeded
```yaml
test_id: ERROR-002
name: Handle 429 rate limit
scenario: Too many API requests
mock_api_response:
  status: 429
  error: "Rate limit exceeded"
  retry_after: 60
expected_behavior:
  - detect: rate_limit_error
  - action: exponential_backoff
  - wait: 60 seconds
  - retry: same operation
  - report: "Rate limit exceeded. Retrying in 60 seconds..."
pass_criteria: Retry with backoff implemented
priority: HIGH
```

### TEST-ERROR-003: Message Not Found
```yaml
test_id: ERROR-003
name: Handle 404 message not found
scenario: User tries to read deleted message
mock_api_response:
  status: 404
  error: "Message not found"
expected_behavior:
  - detect: not_found_error
  - action: report_to_user
    message: "Email not found. It may have been deleted."
  - suggest: "Would you like to search for a different email?"
pass_criteria: Helpful alternative suggested
priority: MEDIUM
```

### TEST-ERROR-004: Invalid Parameters
```yaml
test_id: ERROR-004
name: Handle 400 invalid params
scenario: Malformed query string
mock_api_response:
  status: 400
  error: "Invalid query"
expected_behavior:
  - detect: invalid_params_error
  - action: log_error
  - retry: with corrected params OR
  - report: "Invalid request. Let me try a different approach."
pass_criteria: Graceful fallback attempted
priority: MEDIUM
```

### TEST-ERROR-005: Empty Search Results
```yaml
test_id: ERROR-005
name: Handle zero results from search
user_input: "Show emails from nonexistent@example.com"
expected_workflow:
  - tool: GmailFetchEmails(query="from:nonexistent@example.com")
  - result: 0 emails
  - action: report_empty
    message: "No emails found from nonexistent@example.com."
  - suggest:
      - "Try a different sender"
      - "Check your spam folder"
      - "Search by subject or keyword"
pass_criteria: Helpful suggestions provided
priority: MEDIUM
```

### TEST-ERROR-006: Network Timeout
```yaml
test_id: ERROR-006
name: Handle network timeout
scenario: Request takes too long
mock_api_response:
  timeout: true
expected_behavior:
  - detect: timeout_error
  - retry: with exponential backoff (3 attempts)
  - if_all_fail: report "Network timeout. Please try again later."
pass_criteria: Retry logic with max attempts
priority: HIGH
```

### TEST-ERROR-007: Missing Context
```yaml
test_id: ERROR-007
name: Handle missing required context
user_input: "Delete this email"
context: {}  # Empty - no message_id
expected_behavior:
  - detect: missing_context
  - action: request_clarification
    message: "Which email would you like to delete? You can say:
      - The latest email
      - Email from [person]
      - Email about [topic]"
pass_criteria: Asks for missing information
priority: HIGH
```

### TEST-ERROR-008: Invalid Email Address
```yaml
test_id: ERROR-008
name: Handle malformed email address
user_input: "Send email to john.example.com"  # Missing @
expected_behavior:
  - detect: invalid_email_format
  - action: attempt_correction
    suggestion: "john@example.com"
  - ask: "Did you mean john@example.com? (yes/no/enter correct email)"
pass_criteria: Autocorrection attempted
priority: MEDIUM
```

### TEST-ERROR-009: Permission Denied
```yaml
test_id: ERROR-009
name: Handle 403 permission error
scenario: Missing required Gmail scope
mock_api_response:
  status: 403
  error: "Insufficient permissions"
  required_scope: "gmail.modify"
expected_behavior:
  - detect: permission_error
  - action: report_to_user
    message: "Missing permission: gmail.modify. Please update Gmail connection permissions."
  - provide: permission_update_link
pass_criteria: Clear permission guidance
priority: HIGH
```

### TEST-ERROR-010: Server Error Retry
```yaml
test_id: ERROR-010
name: Handle 500 server error with retry
scenario: Gmail API temporary failure
mock_api_response:
  status: 500
  error: "Internal server error"
expected_behavior:
  - detect: server_error
  - retry: with exponential backoff
    attempts: [1s, 2s, 4s]
  - if_all_fail: "Gmail is temporarily unavailable. Please try again later."
pass_criteria: Retry with backoff, then report
priority: HIGH
```

---

## Test Category 7: Ambiguity Resolution (7 tests)

### TEST-AMBIGUITY-001: Delete Trash vs Permanent
```yaml
test_id: AMBIGUITY-001
name: Clarify delete type when ambiguous
user_input: "Delete emails from spam@example.com"
expected_behavior:
  - detect: delete_ambiguous
  - action: request_clarification
    prompt: "Would you like to:
      1. Move to trash (recoverable for 30 days) ← RECOMMENDED
      2. Permanently delete (CANNOT recover)
      Which would you prefer?"
  - default_if_no_response: option_1 (trash)
pass_criteria: Clarification requested, safer default used
priority: HIGH
```

### TEST-AMBIGUITY-002: Single vs Thread Scope
```yaml
test_id: AMBIGUITY-002
name: Clarify message vs thread operation
user_input: "Label this as Important"
context:
  message_id: "msg_123"
  thread_id: "thread_456"
expected_behavior:
  - detect: scope_ambiguous
  - action: request_clarification
    prompt: "Would you like to:
      1. Label just this message
      2. Label the entire conversation"
pass_criteria: Scope clarification requested
priority: MEDIUM
```

### TEST-AMBIGUITY-003: Multiple Contact Matches
```yaml
test_id: AMBIGUITY-003
name: Disambiguate multiple contacts
user_input: "Email John about the meeting"
expected_workflow:
  - tool: GmailSearchPeople(query="John")
  - result: 3 Johns
  - action: present_options
  - wait: user_selection
  - proceed: with selected contact
pass_criteria: All matches presented for selection
priority: HIGH
```

### TEST-AMBIGUITY-004: Send Mode Unclear
```yaml
test_id: AMBIGUITY-004
name: Clarify immediate send vs draft
user_input: "Email Sarah about vacation"
expected_behavior:
  - detect: send_mode_ambiguous
  - action: request_clarification
    prompt: "Would you like to:
      1. Create draft for review first ← RECOMMENDED
      2. Send immediately"
  - default_if_no_response: draft_mode (safer)
pass_criteria: Send mode clarified, defaults to draft
priority: MEDIUM
```

### TEST-AMBIGUITY-005: Vague Reference
```yaml
test_id: AMBIGUITY-005
name: Handle vague reference like "this"
user_input: "Archive this"
context: {}  # No message_id or thread_id
expected_behavior:
  - detect: vague_reference
  - action: request_clarification
    prompt: "Which email(s) would you like to archive? You can say:
      - The latest email
      - Emails from [person]
      - Emails about [topic]"
pass_criteria: Asks for specific target
priority: MEDIUM
```

### TEST-AMBIGUITY-006: Fuzzy Time Reference
```yaml
test_id: AMBIGUITY-006
name: Interpret fuzzy time like "recent"
user_input: "Show recent emails"
expected_behavior:
  - detect: fuzzy_time
  - interpret: "recent" → "newer_than:3d"
  - tool: GmailFetchEmails(query="newer_than:3d")
  - report: "Showing emails from the last 3 days. Need a different range?"
pass_criteria: Reasonable default applied, user can refine
priority: LOW
```

### TEST-AMBIGUITY-007: Operation Unclear
```yaml
test_id: AMBIGUITY-007
name: Handle vague operation like "deal with"
user_input: "Deal with these emails"
expected_behavior:
  - detect: operation_ambiguous
  - action: present_category_options
    options:
      - "Archive them"
      - "Delete them"
      - "Mark as read"
      - "Label them"
      - "Something else"
pass_criteria: Specific operation options presented
priority: LOW
```

---

## Test Category 8: Workflow Validation (5 tests)

### TEST-WORKFLOW-001: Draft Review Send Complete
```yaml
test_id: WORKFLOW-001
name: Full draft workflow completion
user_input_sequence:
  - "Draft email to john@example.com about the project"
  - "Send it"
expected_workflow:
  - step_1: GmailCreateDraft(to="john@example.com", subject="Project")
  - step_2: present_draft_to_user
  - step_3: wait_for_user_input
  - step_4: receive "Send it"
  - step_5: GmailSendDraft(draft_id="{created}")
  - step_6: report_success(message_id="{sent}")
pass_criteria: All workflow steps completed in order
priority: HIGH
```

### TEST-WORKFLOW-002: Search Organize Report
```yaml
test_id: WORKFLOW-002
name: Bulk organize workflow
user_input_sequence:
  - "Archive all emails from newsletters"
  - "yes"  # Confirmation
expected_workflow:
  - step_1: GmailFetchEmails(query="from:*newsletter*")
  - step_2: count_results (e.g., 34 emails)
  - step_3: present_confirmation (count > 10)
  - step_4: receive "yes"
  - step_5: extract_message_ids
  - step_6: GmailBatchModifyMessages(message_ids, remove_label_ids=["INBOX"])
  - step_7: report "Archived 34 emails from newsletters"
pass_criteria: Workflow handles bulk operation correctly
priority: HIGH
```

### TEST-WORKFLOW-003: Contact Disambiguate Email
```yaml
test_id: WORKFLOW-003
name: Contact search then email workflow
user_input_sequence:
  - "Send email to John"
  - "John Smith"  # Disambiguation
expected_workflow:
  - step_1: GmailSearchPeople(query="John")
  - step_2: find_multiple_results (3 Johns)
  - step_3: present_options
  - step_4: receive "John Smith"
  - step_5: extract_email "john.smith@company.com"
  - step_6: GmailSendEmail(to="john.smith@company.com")
pass_criteria: Disambiguation handled correctly
priority: MEDIUM
```

### TEST-WORKFLOW-004: Draft Revision Approval
```yaml
test_id: WORKFLOW-004
name: Draft revision before sending
user_input_sequence:
  - "Draft email to sarah@example.com"
  - "Make the subject more specific"
  - "Send it now"
expected_workflow:
  - step_1: GmailCreateDraft (initial)
  - step_2: present_draft
  - step_3: receive "Make subject more specific"
  - step_4: ReviseEmailDraft(changes="...")
  - step_5: present_revised_draft
  - step_6: receive "Send it now"
  - step_7: GmailSendDraft
pass_criteria: Revision loop handled correctly
priority: MEDIUM
```

### TEST-WORKFLOW-005: Bulk Delete Safe Workflow
```yaml
test_id: WORKFLOW-005
name: Safe bulk delete with trash
user_input_sequence:
  - "Delete all spam emails"
  - "Move to trash"  # Safer option
expected_workflow:
  - step_1: GmailFetchEmails(query="label:SPAM")
  - step_2: count: 28 emails
  - step_3: present_options (trash vs permanent)
  - step_4: receive "Move to trash"
  - step_5: loop: for each message_id → GmailMoveToTrash
  - step_6: report "Moved 28 emails to trash (recoverable for 30 days)"
pass_criteria: Bulk trash operation executed safely
priority: HIGH
```

---

## Test Execution Guidelines

### Priority Levels
- **CRITICAL**: Must pass 100% - Safety-related tests
- **HIGH**: Must pass 95% - Core routing functionality
- **MEDIUM**: Must pass 90% - Important features
- **LOW**: Must pass 80% - Nice-to-have features

### Test Environment Setup
```yaml
test_environment:
  mock_gmail_api: true
  use_test_credentials: true
  test_email_account: "test@example.com"
  test_contacts:
    - name: "John Smith"
      email: "john.smith@example.com"
    - name: "John Doe"
      email: "john.doe@example.com"
    - name: "Sarah Johnson"
      email: "sarah@company.com"
  test_labels:
    - "INBOX"
    - "STARRED"
    - "IMPORTANT"
    - "ProjectX"
    - "Work"
  test_messages:
    - id: "msg_123"
      from: "john@example.com"
      subject: "Meeting"
      labels: ["INBOX", "UNREAD"]
    - id: "msg_456"
      from: "sarah@example.com"
      subject: "Project Update"
      labels: ["INBOX", "STARRED"]
```

### Reporting Format
```yaml
test_report:
  test_id: "FETCH-001"
  status: "PASS" | "FAIL"
  execution_time_ms: 123
  expected_tool: "GmailFetchEmails"
  actual_tool: "GmailFetchEmails"
  expected_params: {...}
  actual_params: {...}
  assertions:
    - assertion: "Tool called correctly"
      status: "PASS"
    - assertion: "Params match expected"
      status: "PASS"
  notes: "Optional notes"
```

---

**END OF TEST CASES**

Total Tests: 75
Critical Tests: 15 (all delete safety)
High Priority: 35
Medium Priority: 20
Low Priority: 5
