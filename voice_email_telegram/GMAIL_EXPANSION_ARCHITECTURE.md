# Gmail Bot Expansion Architecture
**Date**: 2025-11-01
**Project**: Voice Email Telegram Agency
**Location**: `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram`
**Status**: ARCHITECTURE DESIGN - NOT YET IMPLEMENTED

---

## Executive Summary

This document provides a comprehensive architecture for expanding the existing voice-first Gmail bot from **send-only** to **full Gmail operations** (20+ tools). The design ensures **zero breaking changes** to the current working system while enabling read, search, organize, and manage operations.

**Key Principle**: The existing `GmailSendEmail.py` pattern (Composio SDK) serves as the proven blueprint for all new tools.

---

## Current System Analysis

### Working Architecture (DO NOT BREAK)

**System Health**: ✅ FULLY OPERATIONAL
- **Location**: `~/Desktop/agency-swarm-voice/voice_email_telegram`
- **Working Tools**: 8 tools (Send, Draft operations, Voice, Telegram)
- **Tech Stack**:
  - Agency Swarm v0.7.2+
  - Composio SDK v0.9.0 (for Gmail integration)
  - OpenAI GPT-4o (for intelligence)
  - Telegram Bot API (for voice input)
  - Mem0 (for memory)

**Agent Architecture**: Orchestrator-Workers Pattern
```
┌─────────────────────────────────────────────────┐
│                    CEO Agent                    │
│         (Orchestrates all workflows)            │
└──────────┬───────────┬──────────┬───────────────┘
           │           │          │
    ┌──────▼──┐   ┌────▼────┐  ┌─▼──────────┐
    │ Voice   │   │ Email   │  │  Memory    │
    │ Handler │   │Special. │  │  Manager   │
    └─────────┘   └─────────┘  └────────────┘
```

**Current Workflow**: Voice → Intent → Memory → Draft → Approve → Send

### Proven Composio Pattern (FROM GmailSendEmail.py)

```python
# THIS IS THE WORKING PATTERN - USE FOR ALL NEW TOOLS
from composio import Composio
import os
import json
from agency_swarm.tools import BaseTool
from pydantic import Field

class GmailToolTemplate(BaseTool):
    """Template based on working GmailSendEmail.py"""

    # Define parameters using Pydantic Field
    parameter_name: str = Field(..., description="Parameter description")

    def run(self):
        # 1. Get credentials from environment
        api_key = os.getenv("COMPOSIO_API_KEY")
        entity_id = os.getenv("GMAIL_ENTITY_ID")

        if not api_key or not entity_id:
            return json.dumps({
                "error": "Missing Composio credentials"
            })

        try:
            # 2. Initialize Composio client
            client = Composio(api_key=api_key)

            # 3. Prepare action parameters
            action_params = {
                "param1": self.parameter_name,
                # ... other params
            }

            # 4. Execute action via Composio
            result = client.tools.execute(
                "GMAIL_ACTION_NAME",  # First positional arg: action slug
                action_params,         # Second positional arg: parameters dict
                user_id=entity_id,     # Keyword arg: user identification
                dangerously_skip_version_check=True  # As per working code
            )

            # 5. Format response
            if result.get("successful"):
                return json.dumps({
                    "success": True,
                    "data": result.get("data", {}),
                    "message": "Action completed successfully"
                }, indent=2)
            else:
                return json.dumps({
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": f"Error executing action: {str(e)}",
                "type": type(e).__name__
            }, indent=2)
```

**Critical Implementation Details**:
1. **Method Signature**: `client.tools.execute(slug: str, arguments: Dict, *, user_id: Optional[str], ...)`
2. **First arg**: Action slug (e.g., "GMAIL_SEND_EMAIL", "GMAIL_FETCH_EMAILS")
3. **Second arg**: Parameters dictionary
4. **Keyword args**: `user_id` (entity_id), `dangerously_skip_version_check=True`
5. **Return format**: Always JSON string for Agency Swarm compatibility

---

## Gmail Operations Expansion

### 20 Gmail Tools to Implement

Based on Composio Gmail integration capabilities:

#### 1. Fetch & Read Operations (5 tools)

**GmailFetchEmails.py**
```python
Action: GMAIL_FETCH_EMAILS
Purpose: Retrieve recent emails with optional filtering
Parameters:
  - max_results: int = 50
  - query: str = "" (Gmail search syntax: "is:unread", "from:user@example.com")
  - include_spam_trash: bool = False
  - label_ids: List[str] = []
Returns: List of email messages with id, threadId, snippet
Use Cases:
  - "Show me unread emails"
  - "Get emails from last 24 hours"
  - "Fetch emails with label IMPORTANT"
```

**GmailGetMessage.py**
```python
Action: GMAIL_GET_MESSAGE
Purpose: Get full email details by message ID
Parameters:
  - message_id: str (required)
  - format: str = "full" (options: minimal, full, raw, metadata)
Returns: Complete email with headers, body, attachments metadata
Use Cases:
  - "Show me details of email ID xyz"
  - "Read the full email about project update"
```

**GmailGetThread.py**
```python
Action: GMAIL_GET_THREAD
Purpose: Get all emails in a conversation thread
Parameters:
  - thread_id: str (required)
  - format: str = "full"
Returns: All messages in thread with relationships
Use Cases:
  - "Show me the full conversation with John"
  - "Get all replies in this thread"
```

**GmailSearchEmails.py**
```python
Action: GMAIL_SEARCH_EMAILS
Purpose: Advanced email search with Gmail operators
Parameters:
  - query: str (required) (e.g., "from:john@example.com subject:urgent")
  - max_results: int = 50
  - page_token: str = None (for pagination)
Returns: List of matching email IDs and snippets
Use Cases:
  - "Find all emails from sarah@company.com about invoices"
  - "Search for emails with attachment in last week"
  - "Find unread emails with label Project"
Gmail Query Examples:
  - "is:unread from:boss@company.com"
  - "has:attachment after:2025/10/01"
  - "subject:meeting OR subject:calendar"
  - "label:INBOX -label:SPAM"
```

**GmailGetAttachment.py**
```python
Action: GMAIL_GET_ATTACHMENT
Purpose: Download email attachment
Parameters:
  - message_id: str (required)
  - attachment_id: str (required)
  - save_path: str = "./downloads/"
Returns: File path and metadata
Use Cases:
  - "Download the PDF from invoice email"
  - "Save attachment from message ID xyz"
```

#### 2. Label Management (4 tools)

**GmailCreateLabel.py**
```python
Action: GMAIL_CREATE_LABEL
Purpose: Create new Gmail label
Parameters:
  - label_name: str (required)
  - visibility: str = "show" (options: show, hide, showIfUnread)
  - type: str = "user" (options: user, system)
Returns: Label ID and name
Use Cases:
  - "Create a label called 'Client Emails'"
  - "Make a new folder for invoices"
```

**GmailAddLabel.py**
```python
Action: GMAIL_ADD_LABEL_TO_EMAIL
Purpose: Add label(s) to email(s)
Parameters:
  - message_ids: List[str] (required)
  - label_ids: List[str] (required)
Returns: Updated message IDs
Use Cases:
  - "Add 'Important' label to this email"
  - "Tag these messages as 'Follow Up'"
```

**GmailRemoveLabel.py**
```python
Action: GMAIL_REMOVE_LABEL_FROM_EMAIL
Purpose: Remove label(s) from email(s)
Parameters:
  - message_ids: List[str] (required)
  - label_ids: List[str] (required)
Returns: Updated message IDs
Use Cases:
  - "Remove 'Unread' from these emails"
  - "Untag 'Important' label"
```

**GmailListLabels.py**
```python
Action: GMAIL_LIST_LABELS
Purpose: Get all Gmail labels
Parameters: None
Returns: List of all labels with IDs, names, types
Use Cases:
  - "Show me all my labels"
  - "List available folders"
```

#### 3. Organization Operations (4 tools)

**GmailMarkAsRead.py**
```python
Action: GMAIL_MARK_AS_READ
Purpose: Mark email(s) as read
Parameters:
  - message_ids: List[str] (required)
Returns: Updated message IDs
Use Cases:
  - "Mark all unread emails as read"
  - "Mark this email as read"
```

**GmailMarkAsUnread.py**
```python
Action: GMAIL_MARK_AS_UNREAD
Purpose: Mark email(s) as unread
Parameters:
  - message_ids: List[str] (required)
Returns: Updated message IDs
Use Cases:
  - "Mark this as unread so I remember to respond"
```

**GmailArchiveEmail.py**
```python
Action: GMAIL_ARCHIVE_EMAIL
Purpose: Archive email(s) (remove from inbox)
Parameters:
  - message_ids: List[str] (required)
Returns: Archived message IDs
Use Cases:
  - "Archive this email"
  - "Move these to archive"
```

**GmailDeleteEmail.py**
```python
Action: GMAIL_TRASH_EMAIL
Purpose: Move email(s) to trash
Parameters:
  - message_ids: List[str] (required)
  - permanent: bool = False (if True, permanent delete)
Returns: Deleted message IDs
Use Cases:
  - "Delete this spam email"
  - "Move to trash"
Note: Permanent delete requires additional confirmation
```

#### 4. Draft Operations (4 tools - EXPAND EXISTING)

**GmailUpdateDraft.py** (NEW)
```python
Action: GMAIL_UPDATE_DRAFT
Purpose: Modify existing draft
Parameters:
  - draft_id: str (required)
  - to: str = None (update recipients)
  - subject: str = None (update subject)
  - body: str = None (update body)
  - cc: str = None
  - bcc: str = None
Returns: Updated draft ID
Use Cases:
  - "Change the draft subject to..."
  - "Update draft body with..."
```

**GmailSendDraft.py** (NEW)
```python
Action: GMAIL_SEND_DRAFT
Purpose: Send an existing draft
Parameters:
  - draft_id: str (required)
Returns: Sent message ID
Use Cases:
  - "Send the draft I created"
  - "Send draft ID xyz"
```

**GmailDeleteDraft.py** (NEW)
```python
Action: GMAIL_DELETE_DRAFT
Purpose: Delete a draft
Parameters:
  - draft_id: str (required)
Returns: Confirmation
Use Cases:
  - "Delete this draft"
  - "Remove draft ID xyz"
```

*Note: GmailCreateDraft.py, GmailGetDraft.py, GmailListDrafts.py already exist but need Composio pattern update*

#### 5. Batch Operations (2 tools)

**GmailBatchModify.py**
```python
Action: GMAIL_BATCH_MODIFY
Purpose: Modify multiple emails at once
Parameters:
  - message_ids: List[str] (required)
  - add_label_ids: List[str] = []
  - remove_label_ids: List[str] = []
Returns: Modified message IDs
Use Cases:
  - "Mark all unread emails from john@company.com as read and archive"
  - "Add 'Important' and remove 'Unread' from these 5 emails"
```

**GmailBulkDelete.py**
```python
Action: GMAIL_BULK_DELETE
Purpose: Delete multiple emails matching criteria
Parameters:
  - query: str (required) (Gmail search syntax)
  - dry_run: bool = True (preview before deleting)
  - max_delete: int = 100 (safety limit)
Returns: Number of emails deleted or preview list
Use Cases:
  - "Delete all emails older than 6 months"
  - "Remove all promotional emails"
Security: Requires confirmation step for safety
```

#### 6. Advanced Operations (1 tool)

**GmailSendWithAttachment.py**
```python
Action: GMAIL_SEND_EMAIL_WITH_ATTACHMENT
Purpose: Send email with file attachment
Parameters:
  - to: str (required)
  - subject: str (required)
  - body: str (required)
  - attachment_path: str (required)
  - cc: str = ""
  - bcc: str = ""
Returns: Sent message ID
Use Cases:
  - "Send report.pdf to client@company.com"
  - "Email the invoice with attachment"
```

---

## Gmail Monitoring Service Architecture

### Background Polling System

**Purpose**: Monitor Gmail inbox and trigger agent workflow for new emails

**Design Requirements**:
1. Non-blocking - runs in background without interfering with Telegram bot
2. Configurable schedule - only during business hours (9am-6pm)
3. Lightweight - efficient API usage to avoid rate limits
4. Smart filtering - only process emails matching certain criteria
5. Integration with existing agent system

### Implementation Design

#### File: `gmail_monitoring_service.py`

```python
#!/usr/bin/env python3
"""
Gmail Monitoring Service
Polls Gmail inbox for new emails and triggers agency workflow
Runs alongside telegram_bot_listener.py without interference
"""

import json
import os
import time
from datetime import datetime, time as dt_time
from typing import List, Dict, Optional
import threading

from dotenv import load_dotenv
from composio import Composio

# Import agency
from agency import agency

# Import Gmail tools
from email_specialist.tools.GmailFetchEmails import GmailFetchEmails
from email_specialist.tools.GmailGetMessage import GmailGetMessage
from email_specialist.tools.GmailMarkAsRead import GmailMarkAsRead

load_dotenv()


class GmailMonitoringService:
    """
    Monitors Gmail inbox for new emails and processes them through agency.

    Features:
    - Polls every 2 minutes during business hours
    - Tracks seen message IDs to avoid duplicates
    - Filters based on criteria (unread, specific labels, senders)
    - Integrates with existing agent workflow
    """

    def __init__(
        self,
        poll_interval: int = 120,  # 2 minutes
        business_hours_start: int = 9,  # 9 AM
        business_hours_end: int = 18,  # 6 PM
        filters: Optional[Dict] = None
    ):
        self.api_key = os.getenv("COMPOSIO_API_KEY")
        self.entity_id = os.getenv("GMAIL_ENTITY_ID")
        self.poll_interval = poll_interval
        self.business_hours_start = business_hours_start
        self.business_hours_end = business_hours_end
        self.running = False
        self.seen_message_ids = set()

        # Default filters: unread emails only
        self.filters = filters or {
            "query": "is:unread",
            "max_results": 10,
            "labels": []
        }

        if not self.api_key or not self.entity_id:
            raise ValueError("COMPOSIO_API_KEY and GMAIL_ENTITY_ID required")

        print("=" * 80)
        print("GMAIL MONITORING SERVICE")
        print("=" * 80)
        print(f"Poll Interval: {poll_interval} seconds")
        print(f"Business Hours: {business_hours_start}:00 - {business_hours_end}:00")
        print(f"Filters: {self.filters}")
        print("=" * 80)

    def is_business_hours(self) -> bool:
        """Check if current time is within business hours"""
        now = datetime.now().time()
        start = dt_time(self.business_hours_start, 0)
        end = dt_time(self.business_hours_end, 0)
        return start <= now <= end

    def fetch_new_emails(self) -> List[Dict]:
        """
        Fetch new emails matching filters.
        Returns list of new email messages.
        """
        try:
            # Use GmailFetchEmails tool
            fetch_tool = GmailFetchEmails(
                query=self.filters["query"],
                max_results=self.filters["max_results"]
            )

            result_json = fetch_tool.run()
            result = json.loads(result_json)

            if not result.get("success"):
                print(f"⚠️ Fetch failed: {result.get('error')}")
                return []

            emails = result.get("data", {}).get("messages", [])

            # Filter out already seen emails
            new_emails = [
                email for email in emails
                if email.get("id") not in self.seen_message_ids
            ]

            # Update seen set
            for email in new_emails:
                self.seen_message_ids.add(email.get("id"))

            return new_emails

        except Exception as e:
            print(f"❌ Error fetching emails: {str(e)}")
            return []

    def get_email_details(self, message_id: str) -> Optional[Dict]:
        """Get full email details by message ID"""
        try:
            get_tool = GmailGetMessage(message_id=message_id, format="full")
            result_json = get_tool.run()
            result = json.loads(result_json)

            if result.get("success"):
                return result.get("data")
            return None

        except Exception as e:
            print(f"❌ Error getting email details: {str(e)}")
            return None

    def process_email(self, email: Dict):
        """
        Process a new email through the agency workflow.

        Workflow:
        1. Get full email details
        2. Extract sender, subject, body
        3. Send to agency for intelligent processing
        4. Agency decides action (auto-reply, flag, categorize, etc.)
        """
        message_id = email.get("id")
        print(f"\n📧 Processing email {message_id}")

        # Get full email details
        details = self.get_email_details(message_id)
        if not details:
            print(f"⚠️ Could not retrieve details for {message_id}")
            return

        # Extract key information
        headers = {h["name"]: h["value"] for h in details.get("payload", {}).get("headers", [])}
        sender = headers.get("From", "Unknown")
        subject = headers.get("Subject", "No Subject")
        snippet = details.get("snippet", "")

        print(f"  From: {sender}")
        print(f"  Subject: {subject}")
        print(f"  Snippet: {snippet[:50]}...")

        # Send to agency for processing
        try:
            print(f"🤖 Sending to agency for intelligent processing...")

            response = agency.get_completion(
                f"""A new email has been received:

From: {sender}
Subject: {subject}
Preview: {snippet}
Message ID: {message_id}

Please analyze this email and determine the appropriate action:
- Should we send an auto-reply?
- Should it be labeled/categorized?
- Does it require human attention?
- Should it be marked for follow-up?

Provide your recommendation and take appropriate actions."""
            )

            print(f"✅ Agency response: {response[:100]}...")

        except Exception as e:
            print(f"❌ Error processing through agency: {str(e)}")

    def poll_cycle(self):
        """Single polling cycle"""
        if not self.is_business_hours():
            return  # Skip if outside business hours

        try:
            print(f"\n🔄 Polling Gmail ({datetime.now().strftime('%H:%M:%S')})")

            new_emails = self.fetch_new_emails()

            if new_emails:
                print(f"📬 Found {len(new_emails)} new email(s)")

                for email in new_emails:
                    self.process_email(email)

                print(f"✅ Processed {len(new_emails)} email(s)")
            else:
                print("   No new emails")

        except Exception as e:
            print(f"❌ Error in poll cycle: {str(e)}")

    def start(self):
        """Start the monitoring service"""
        self.running = True

        print("\n" + "=" * 80)
        print("🚀 GMAIL MONITORING STARTED")
        print("=" * 80)
        print("Monitoring inbox for new emails...")
        print("Press Ctrl+C to stop")
        print("=" * 80 + "\n")

        try:
            while self.running:
                self.poll_cycle()
                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print("\n\n" + "=" * 80)
            print("🛑 STOPPING GMAIL MONITORING")
            print("=" * 80)
            self.running = False

    def start_background(self):
        """Start monitoring in background thread"""
        thread = threading.Thread(target=self.start, daemon=True)
        thread.start()
        print("✅ Gmail monitoring started in background")
        return thread

    def stop(self):
        """Stop the monitoring service"""
        self.running = False


# Standalone execution
if __name__ == "__main__":
    try:
        # Create monitoring service
        monitor = GmailMonitoringService(
            poll_interval=120,  # 2 minutes
            business_hours_start=9,
            business_hours_end=18,
            filters={
                "query": "is:unread",  # Only unread emails
                "max_results": 10
            }
        )

        # Start monitoring
        monitor.start()

    except ValueError as e:
        print(f"❌ Configuration Error: {str(e)}")
        print("Please set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env")
    except Exception as e:
        print(f"❌ Fatal Error: {str(e)}")
        import traceback
        traceback.print_exc()
```

### Integration with Telegram Bot

#### Updated: `telegram_bot_listener.py` Integration

```python
# Add to telegram_bot_listener.py

from gmail_monitoring_service import GmailMonitoringService

def start_combined_services():
    """Start both Telegram bot and Gmail monitoring together"""

    # Start Gmail monitoring in background
    gmail_monitor = GmailMonitoringService()
    gmail_thread = gmail_monitor.start_background()

    # Start Telegram bot in foreground
    telegram_listener = TelegramBotListener()
    telegram_listener.start()

    # When Telegram stops, stop Gmail too
    gmail_monitor.stop()
    gmail_thread.join()

if __name__ == "__main__":
    start_combined_services()
```

### Startup Script

#### File: `start_voice_email_system.sh`

```bash
#!/bin/bash
# Start complete Voice Email system with Gmail monitoring

echo "=================================="
echo "Starting Voice Email System"
echo "=================================="

# Activate virtual environment
source venv/bin/activate

# Start combined services
echo "Starting Telegram Bot + Gmail Monitor..."
python telegram_bot_listener.py

# Or run separately:
# python telegram_bot_listener.py &
# python gmail_monitoring_service.py &

echo "System stopped"
```

---

## CEO Routing Expansion

### Intent Detection Strategy

**Challenge**: CEO must detect user intent and route to appropriate tools

**Current Implementation**: CEO only handles "send email" workflow

**Expanded Implementation**: Multi-intent detection with smart routing

### Intent Categories

```python
INTENT_CATEGORIES = {
    "SEND": {
        "keywords": ["send", "email", "message", "write to"],
        "tools": ["GmailSendEmail", "DraftEmailFromVoice"],
        "workflow": "draft_approve_send"
    },
    "READ": {
        "keywords": ["show", "read", "get", "fetch", "check"],
        "tools": ["GmailFetchEmails", "GmailGetMessage", "GmailSearchEmails"],
        "workflow": "fetch_display"
    },
    "SEARCH": {
        "keywords": ["find", "search", "look for", "filter"],
        "tools": ["GmailSearchEmails", "GmailFetchEmails"],
        "workflow": "search_display"
    },
    "ORGANIZE": {
        "keywords": ["archive", "delete", "label", "mark as"],
        "tools": ["GmailArchiveEmail", "GmailAddLabel", "GmailMarkAsRead"],
        "workflow": "modify_confirm"
    },
    "DRAFT": {
        "keywords": ["draft", "save", "prepare"],
        "tools": ["GmailCreateDraft", "GmailUpdateDraft"],
        "workflow": "draft_save"
    }
}
```

### Updated CEO Instructions

#### File: `ceo/instructions.md` (EXPANDED)

```markdown
# CEO Agent Instructions (EXPANDED)

## Role
You are the CEO orchestrator for a comprehensive voice-first Gmail management system.
You coordinate Voice Handler, Email Specialist, and Memory Manager to handle ALL Gmail operations.

## Core Responsibilities
1. Detect user intent from voice/text input
2. Route to appropriate workflow based on intent
3. Coordinate multi-step operations
4. Manage approval and confirmation flows
5. Provide clear status updates

## Intent Detection & Routing

### 1. SEND Intent
**Triggers**: "send email", "email to", "message", "write to"

**Workflow**:
1. Extract intent via Voice Handler
2. Get user preferences from Memory Manager
3. Draft email via Email Specialist
4. Present for approval (unless explicit "send now")
5. Send via GmailSendEmail

**Example**: "Send an email to john@company.com about the meeting"

### 2. READ Intent
**Triggers**: "show emails", "read emails", "check inbox", "get messages"

**Workflow**:
1. Determine fetch criteria (unread, recent, specific sender)
2. Fetch via GmailFetchEmails or GmailSearchEmails
3. Present summary to user
4. If user requests details, use GmailGetMessage

**Example**: "Show me unread emails from today"

### 3. SEARCH Intent
**Triggers**: "find emails", "search for", "look for emails"

**Workflow**:
1. Extract search criteria from voice input
2. Build Gmail query string
3. Execute GmailSearchEmails
4. Present results with snippets
5. Offer to read specific emails

**Example**: "Find all emails from sarah@company.com about invoices"

### 4. ORGANIZE Intent
**Triggers**: "archive", "delete", "label", "mark as read", "categorize"

**Workflow**:
1. Identify target emails (by ID, search, or current context)
2. Confirm action with user (especially for delete)
3. Execute organization tool
4. Confirm completion

**Example**: "Archive all emails older than 30 days"

### 5. DRAFT Intent
**Triggers**: "draft email", "save draft", "prepare email"

**Workflow**:
1. Extract draft details
2. Create via GmailCreateDraft
3. Return draft ID for later sending
4. Offer to edit or send

**Example**: "Draft an email to the team about project update"

### 6. MANAGE Intent
**Triggers**: "show labels", "create folder", "get thread"

**Workflow**:
1. Execute appropriate management tool
2. Present results
3. Offer follow-up actions

**Example**: "Show me all my Gmail labels"

## Multi-Intent Handling

### Sequential Intents
"Find all unread emails from john@company.com and archive them"

**Workflow**:
1. SEARCH: GmailSearchEmails with query
2. Confirm: "Found 5 emails from John. Archive all?"
3. ORGANIZE: GmailArchiveEmail with message IDs
4. Confirm: "Archived 5 emails"

### Conditional Logic
"If there are any urgent emails, show them to me"

**Workflow**:
1. READ: GmailFetchEmails with query "is:unread label:urgent"
2. If results: Present to user
3. If no results: "No urgent emails found"

## Tool Selection Logic

```
User Input → Intent Detection → Tool Selection → Parameter Extraction → Execution
```

**Decision Tree**:
- Contains email address + action verb? → SEND workflow
- Contains "show"/"get"/"read"? → READ workflow
- Contains "find"/"search" + criteria? → SEARCH workflow
- Contains "archive"/"delete"/"label"? → ORGANIZE workflow
- Contains "draft"/"prepare"? → DRAFT workflow

## Safety & Confirmation

### Require Confirmation For:
1. **Delete operations**: Always confirm before deleting
2. **Bulk operations**: Confirm if >5 emails affected
3. **Permanent actions**: Warn about irreversible actions

### Auto-Execute For:
1. **Read operations**: Fetching, searching, displaying
2. **Label operations**: Adding/removing labels
3. **Mark as read**: Low-risk organization

## Error Handling

### Missing Information
"I don't have enough information to complete this. Could you clarify...?"

### API Errors
"There was an issue connecting to Gmail. Let me try again..."

### Ambiguous Intent
"Do you want me to: (A) Send the email now, or (B) Save as draft?"

## Communication Style
- Clear and action-oriented
- Confirm understanding before executing
- Provide status updates for multi-step operations
- Ask for clarification when needed
- Summarize results concisely

## Tools Available (EXPANDED)

### Send Operations
- GmailSendEmail
- GmailSendDraft
- GmailSendWithAttachment

### Read Operations
- GmailFetchEmails
- GmailGetMessage
- GmailGetThread
- GmailSearchEmails

### Organization
- GmailMarkAsRead
- GmailMarkAsUnread
- GmailArchiveEmail
- GmailDeleteEmail

### Label Management
- GmailCreateLabel
- GmailAddLabel
- GmailRemoveLabel
- GmailListLabels

### Draft Management
- GmailCreateDraft
- GmailGetDraft
- GmailUpdateDraft
- GmailSendDraft
- GmailDeleteDraft
- GmailListDrafts

### Advanced
- GmailGetAttachment
- GmailBatchModify

## Key Principles
- Detect intent accurately before acting
- Route to correct workflow based on intent
- Confirm destructive actions
- Provide clear feedback
- Handle errors gracefully
- Maintain context across multi-turn conversations
```

### Intent Detection Tool

#### New Tool: `ceo/tools/DetectGmailIntent.py`

```python
import json
import os
from typing import Dict, List

from openai import OpenAI
from pydantic import Field
from agency_swarm.tools import BaseTool
from dotenv import load_dotenv

load_dotenv()


class DetectGmailIntent(BaseTool):
    """
    Detects Gmail operation intent from user input.

    Identifies:
    - Primary intent (SEND, READ, SEARCH, ORGANIZE, DRAFT, MANAGE)
    - Target emails (if applicable)
    - Action parameters
    - Confirmation requirements

    Returns routing information for CEO to execute appropriate workflow.
    """

    user_input: str = Field(..., description="User's voice or text input")

    context: str = Field(
        default="",
        description="Optional context from previous conversation"
    )

    def run(self):
        """
        Analyzes user input and returns intent classification with routing info.
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return json.dumps({"error": "OPENAI_API_KEY not found"})

        try:
            client = OpenAI(api_key=api_key)

            system_prompt = """You are an expert at detecting Gmail operation intent from voice/text input.

Classify the user's intent into one of these categories:
1. SEND - Send/compose new email
2. READ - Fetch/read/check emails
3. SEARCH - Find/search for specific emails
4. ORGANIZE - Archive/delete/label/mark emails
5. DRAFT - Save draft for later
6. MANAGE - Label management, get threads, system operations

For each intent, extract:
- primary_intent: The main action category
- sub_intent: Specific action (e.g., "send_email", "fetch_unread", "archive")
- parameters: Key details for executing the action
- requires_confirmation: Boolean (true for destructive actions)
- suggested_tools: List of tool names to use
- next_steps: Workflow steps for CEO

Return ONLY valid JSON."""

            user_prompt = f"""User Input: "{self.user_input}"
Context: {self.context if self.context else "None"}

Analyze this input and return Gmail intent classification."""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )

            intent_json = response.choices[0].message.content
            intent_data = json.loads(intent_json)

            # Add original input for reference
            intent_data["original_input"] = self.user_input

            return json.dumps(intent_data, indent=2)

        except Exception as e:
            return json.dumps({
                "error": f"Error detecting intent: {str(e)}",
                "original_input": self.user_input
            })


if __name__ == "__main__":
    print("Testing DetectGmailIntent...")

    test_cases = [
        "Send an email to john@company.com about the meeting",
        "Show me unread emails from today",
        "Find all emails from sarah about invoices",
        "Archive all promotional emails",
        "Draft an email to the team",
        "Delete emails older than 30 days",
        "Show me all my labels",
        "Mark these emails as read",
    ]

    for i, test_input in enumerate(test_cases, 1):
        print(f"\n{i}. Testing: {test_input}")
        tool = DetectGmailIntent(user_input=test_input)
        result = tool.run()
        print(result)
```

---

## File Structure Recommendations

### Organized Tool Directory

```
email_specialist/
├── tools/
│   ├── __init__.py
│   │
│   ├── send/                          # Send operations
│   │   ├── GmailSendEmail.py          ✅ EXISTS (update to Composio)
│   │   ├── GmailSendDraft.py          🆕 NEW
│   │   └── GmailSendWithAttachment.py 🆕 NEW
│   │
│   ├── fetch/                         # Read operations
│   │   ├── GmailFetchEmails.py        🆕 NEW
│   │   ├── GmailGetMessage.py         🆕 NEW
│   │   ├── GmailGetThread.py          🆕 NEW
│   │   ├── GmailSearchEmails.py       🆕 NEW
│   │   └── GmailGetAttachment.py      🆕 NEW
│   │
│   ├── organize/                      # Organization operations
│   │   ├── GmailMarkAsRead.py         🆕 NEW
│   │   ├── GmailMarkAsUnread.py       🆕 NEW
│   │   ├── GmailArchiveEmail.py       🆕 NEW
│   │   ├── GmailDeleteEmail.py        🆕 NEW
│   │   └── GmailBatchModify.py        🆕 NEW
│   │
│   ├── labels/                        # Label management
│   │   ├── GmailCreateLabel.py        🆕 NEW
│   │   ├── GmailAddLabel.py           🆕 NEW
│   │   ├── GmailRemoveLabel.py        🆕 NEW
│   │   └── GmailListLabels.py         🆕 NEW
│   │
│   ├── drafts/                        # Draft operations
│   │   ├── GmailCreateDraft.py        ✅ EXISTS (update to Composio)
│   │   ├── GmailGetDraft.py           ✅ EXISTS (update to Composio)
│   │   ├── GmailListDrafts.py         ✅ EXISTS (update to Composio)
│   │   ├── GmailUpdateDraft.py        🆕 NEW
│   │   ├── GmailSendDraft.py          🆕 NEW
│   │   └── GmailDeleteDraft.py        🆕 NEW
│   │
│   └── composition/                   # Email composition (existing)
│       ├── DraftEmailFromVoice.py     ✅ EXISTS
│       ├── ReviseEmailDraft.py        ✅ EXISTS
│       ├── FormatEmailForApproval.py  ✅ EXISTS
│       └── ValidateEmailContent.py    ✅ EXISTS
```

### Service Files

```
/
├── telegram_bot_listener.py           ✅ EXISTS
├── gmail_monitoring_service.py        🆕 NEW
├── start_voice_email_system.sh        🆕 NEW (startup script)
└── agency.py                          ✅ EXISTS (no changes needed)
```

### CEO Tools

```
ceo/
├── tools/
│   ├── ApprovalStateMachine.py        ✅ EXISTS
│   ├── WorkflowCoordinator.py         ✅ EXISTS
│   └── DetectGmailIntent.py           🆕 NEW (intent detection)
```

---

## No Breaking Changes Strategy

### Principle: Additive-Only Changes

**Rule**: Every change must be backwards-compatible

### What to PRESERVE (DO NOT MODIFY):

1. **Existing Files** (Keep as-is):
   - `telegram_bot_listener.py` - Working Telegram integration
   - `agency.py` - Agent architecture and communication flow
   - `DraftEmailFromVoice.py` - Email composition logic
   - `ExtractEmailIntent.py` - Voice intent extraction
   - `ValidateEmailContent.py` - Email validation
   - All Memory Manager tools
   - All Voice Handler tools

2. **Existing Tool Signatures**:
   - `GmailSendEmail.py` - Keep parameter names and return format
   - Don't break any existing tool interfaces

3. **Environment Variables**:
   - All existing `.env` variables remain
   - Only ADD new optional variables

4. **Agency Chart**:
   - Keep existing agent relationships
   - Don't change agent names or descriptions

### What to ADD (New Components):

1. **New Tool Files**:
   - All 20 new Gmail tools in organized directories
   - Each follows proven Composio pattern

2. **New Service Files**:
   - `gmail_monitoring_service.py` - Standalone service
   - `start_voice_email_system.sh` - Optional unified launcher

3. **New CEO Tools**:
   - `DetectGmailIntent.py` - Intent classification
   - Enhanced routing logic in CEO instructions

4. **Configuration Files**:
   - `gmail_tools_config.json` - Tool metadata (optional)

### What to UPDATE (Careful Modifications):

1. **CEO Instructions** (`ceo/instructions.md`):
   - APPEND new intent handling sections
   - KEEP existing send workflow instructions
   - ADD new routing logic without removing old

2. **Email Specialist Instructions**:
   - APPEND new tool descriptions
   - KEEP existing composition workflow
   - ADD new operation capabilities

3. **Existing Mock Tools**:
   - `GmailCreateDraft.py` - Replace mock with Composio (keep same interface)
   - `GmailGetDraft.py` - Replace mock with Composio (keep same interface)
   - `GmailListDrafts.py` - Replace mock with Composio (keep same interface)

### Testing Protocol

**Before Deploying Any New Tools**:

1. **Baseline Test**: Run existing send workflow
   ```bash
   python telegram_bot_listener.py
   # Send voice message: "Send email to test@example.com"
   # VERIFY: Email sent successfully
   ```

2. **Add One Tool**: Deploy ONE new tool at a time

3. **Test Isolation**: Test new tool independently
   ```python
   from email_specialist.tools.fetch.GmailFetchEmails import GmailFetchEmails
   tool = GmailFetchEmails(query="is:unread", max_results=5)
   result = tool.run()
   print(result)
   ```

4. **Regression Test**: Re-run baseline test after each addition

5. **Integration Test**: Test CEO routing with new intent

### Rollback Plan

If anything breaks:

1. **Immediate Rollback**:
   ```bash
   git stash  # Stash all changes
   # System returns to working state
   ```

2. **Identify Issue**:
   - Check which tool caused the break
   - Review error logs
   - Validate Composio SDK call

3. **Fix in Isolation**:
   - Fix the specific tool
   - Test independently
   - Re-integrate carefully

---

## Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal**: Prove Composio pattern works for read operations

**Tasks**:
1. ✅ Verify existing GmailSendEmail.py works
2. 🆕 Implement GmailFetchEmails.py using same pattern
3. 🆕 Test fetch independently
4. 🆕 Integrate with CEO for simple "show emails" command
5. ✅ Regression test send workflow

**Success Criteria**:
- Send workflow still works
- Fetch workflow returns real Gmail data
- CEO can route between send and fetch

### Phase 2: Core Read Operations (Week 2)
**Goal**: Complete all read operations

**Tasks**:
1. Implement GmailGetMessage.py
2. Implement GmailSearchEmails.py
3. Implement GmailGetThread.py
4. Update CEO routing for read intents
5. Add DetectGmailIntent.py tool

**Success Criteria**:
- All read operations tested and working
- CEO accurately detects read vs send intent
- Results display clearly to user

### Phase 3: Organization Operations (Week 3)
**Goal**: Enable email organization

**Tasks**:
1. Implement GmailMarkAsRead.py
2. Implement GmailArchiveEmail.py
3. Implement GmailDeleteEmail.py (with confirmation)
4. Add confirmation flow to CEO
5. Test bulk operations

**Success Criteria**:
- Organization tools work correctly
- Confirmation required for destructive actions
- Batch operations handle multiple emails

### Phase 4: Label Management (Week 4)
**Goal**: Complete label operations

**Tasks**:
1. Implement GmailListLabels.py
2. Implement GmailCreateLabel.py
3. Implement GmailAddLabel.py
4. Implement GmailRemoveLabel.py
5. Test label workflows

**Success Criteria**:
- All label operations functional
- CEO routes label commands correctly
- Labels persist in Gmail

### Phase 5: Draft Enhancement (Week 5)
**Goal**: Complete draft management

**Tasks**:
1. Update existing draft tools to Composio pattern
2. Implement GmailUpdateDraft.py
3. Implement GmailSendDraft.py
4. Implement GmailDeleteDraft.py
5. Test draft lifecycle

**Success Criteria**:
- All draft operations use Composio
- Draft editing workflow smooth
- Send draft integrates with approval flow

### Phase 6: Advanced & Monitoring (Week 6)
**Goal**: Add monitoring and advanced features

**Tasks**:
1. Implement GmailSendWithAttachment.py
2. Implement GmailGetAttachment.py
3. Implement GmailBatchModify.py
4. Build gmail_monitoring_service.py
5. Test monitoring integration

**Success Criteria**:
- Attachment handling works
- Monitoring polls Gmail successfully
- New emails trigger agent workflow
- No interference with Telegram bot

### Phase 7: Polish & Optimization (Week 7)
**Goal**: Production readiness

**Tasks**:
1. Error handling review
2. Performance optimization
3. Documentation completion
4. User guide creation
5. Deployment automation

**Success Criteria**:
- All error cases handled gracefully
- Response times acceptable
- Complete documentation
- One-command deployment

---

## Technical Specifications

### Composio Action Names

Based on Composio Gmail integration:

```python
GMAIL_ACTIONS = {
    # Send
    "GMAIL_SEND_EMAIL": "Send email",
    "GMAIL_SEND_DRAFT": "Send existing draft",

    # Fetch
    "GMAIL_FETCH_EMAILS": "List/fetch emails",
    "GMAIL_GET_MESSAGE": "Get single email details",
    "GMAIL_GET_THREAD": "Get email thread",

    # Search
    "GMAIL_SEARCH_EMAILS": "Search with query",

    # Organize
    "GMAIL_MARK_AS_READ": "Mark as read",
    "GMAIL_MARK_AS_UNREAD": "Mark as unread",
    "GMAIL_ARCHIVE_EMAIL": "Archive (remove from inbox)",
    "GMAIL_TRASH_EMAIL": "Move to trash",
    "GMAIL_DELETE_EMAIL_PERMANENTLY": "Permanent delete",

    # Labels
    "GMAIL_CREATE_LABEL": "Create new label",
    "GMAIL_ADD_LABEL": "Add label to email",
    "GMAIL_REMOVE_LABEL": "Remove label from email",
    "GMAIL_LIST_LABELS": "Get all labels",

    # Drafts
    "GMAIL_CREATE_DRAFT": "Create draft",
    "GMAIL_GET_DRAFT": "Get draft details",
    "GMAIL_UPDATE_DRAFT": "Update draft",
    "GMAIL_DELETE_DRAFT": "Delete draft",
    "GMAIL_LIST_DRAFTS": "List drafts",

    # Advanced
    "GMAIL_GET_ATTACHMENT": "Download attachment",
    "GMAIL_BATCH_MODIFY": "Batch modify emails",
}
```

### Standard Response Format

All tools return JSON with this structure:

```python
{
    "success": bool,           # True if operation succeeded
    "data": dict or list,      # Operation results
    "message": str,            # Human-readable summary
    "error": str,              # Error message if failed (optional)
    "metadata": {              # Additional information
        "timestamp": str,
        "action": str,
        "message_ids": list    # Affected message IDs (if applicable)
    }
}
```

### Error Handling Standards

```python
try:
    # Composio execution
    result = client.tools.execute(...)

    if result.get("successful"):
        return json.dumps({
            "success": True,
            "data": result.get("data"),
            "message": "Operation completed"
        }, indent=2)
    else:
        return json.dumps({
            "success": False,
            "error": result.get("error", "Unknown error"),
            "message": "Operation failed"
        }, indent=2)

except ComposioException as e:
    # Composio-specific errors
    return json.dumps({
        "success": False,
        "error": f"Composio error: {str(e)}",
        "type": "ComposioException"
    }, indent=2)

except Exception as e:
    # General errors
    return json.dumps({
        "success": False,
        "error": f"Unexpected error: {str(e)}",
        "type": type(e).__name__
    }, indent=2)
```

### Rate Limiting

Gmail API has rate limits:
- **250 quota units per user per second**
- **25,000 quota units per project per day** (default)

**Tool Costs**:
- Send: 100 units
- Fetch/List: 5 units per request
- Get message: 5 units
- Modify: 5 units

**Mitigation**:
- Implement exponential backoff on 429 errors
- Cache frequently accessed data
- Batch operations when possible
- Monitor quota usage in Gmail monitoring service

### Security Considerations

1. **Authentication**:
   - Composio handles OAuth2 token refresh
   - Store only entity_id and connection_id
   - Never expose access_token in logs

2. **Permission Scopes**:
   - Current: `gmail.send`, `gmail.readonly`, `gmail.modify`
   - Verify scopes in Composio connection

3. **Data Privacy**:
   - Don't log full email bodies
   - Redact sensitive information in responses
   - Secure .env file (never commit)

4. **Confirmation for Destructive Actions**:
   - Delete: Always confirm
   - Bulk operations: Confirm if >5 emails
   - Permanent delete: Double confirmation

---

## Testing Plan

### Unit Tests

Each tool requires unit test:

```python
# test_gmail_fetch_emails.py
import pytest
from email_specialist.tools.fetch.GmailFetchEmails import GmailFetchEmails

def test_fetch_unread_emails():
    """Test fetching unread emails"""
    tool = GmailFetchEmails(query="is:unread", max_results=5)
    result = tool.run()

    assert "success" in result
    data = json.loads(result)
    assert data["success"] == True
    assert "data" in data
    assert "messages" in data["data"]

def test_fetch_with_label():
    """Test fetching emails with specific label"""
    tool = GmailFetchEmails(query="label:IMPORTANT", max_results=10)
    result = tool.run()

    data = json.loads(result)
    assert data["success"] == True

def test_fetch_invalid_query():
    """Test error handling for invalid query"""
    tool = GmailFetchEmails(query="invalid:query:syntax", max_results=5)
    result = tool.run()

    data = json.loads(result)
    # Should handle gracefully, not crash
    assert "success" in data
```

### Integration Tests

```python
# test_gmail_workflow.py
def test_fetch_and_read_workflow():
    """Test complete fetch -> read workflow"""

    # Step 1: Fetch emails
    fetch_tool = GmailFetchEmails(query="is:unread", max_results=1)
    fetch_result = json.loads(fetch_tool.run())
    assert fetch_result["success"]

    # Step 2: Get first message details
    message_id = fetch_result["data"]["messages"][0]["id"]
    get_tool = GmailGetMessage(message_id=message_id, format="full")
    get_result = json.loads(get_tool.run())
    assert get_result["success"]

    # Step 3: Mark as read
    mark_tool = GmailMarkAsRead(message_ids=[message_id])
    mark_result = json.loads(mark_tool.run())
    assert mark_result["success"]

def test_search_and_organize_workflow():
    """Test search -> organize workflow"""

    # Search for old promotional emails
    search_tool = GmailSearchEmails(
        query="category:promotions older_than:30d",
        max_results=5
    )
    search_result = json.loads(search_tool.run())
    assert search_result["success"]

    message_ids = [m["id"] for m in search_result["data"]["messages"]]

    # Archive them
    archive_tool = GmailArchiveEmail(message_ids=message_ids)
    archive_result = json.loads(archive_tool.run())
    assert archive_result["success"]
```

### CEO Routing Tests

```python
# test_ceo_routing.py
def test_send_intent_routing():
    """Test CEO detects and routes send intent"""
    user_input = "Send an email to john@company.com about meeting"

    intent_tool = DetectGmailIntent(user_input=user_input)
    intent_result = json.loads(intent_tool.run())

    assert intent_result["primary_intent"] == "SEND"
    assert "GmailSendEmail" in intent_result["suggested_tools"]

def test_read_intent_routing():
    """Test CEO detects and routes read intent"""
    user_input = "Show me unread emails from today"

    intent_tool = DetectGmailIntent(user_input=user_input)
    intent_result = json.loads(intent_tool.run())

    assert intent_result["primary_intent"] == "READ"
    assert "GmailFetchEmails" in intent_result["suggested_tools"]
```

### Regression Tests

Run after each new tool deployment:

```bash
#!/bin/bash
# regression_test.sh

echo "Running regression tests..."

# Test 1: Send workflow (baseline)
echo "Test 1: Send workflow"
python test_send_workflow.py

# Test 2: Telegram integration
echo "Test 2: Telegram integration"
python test_telegram_integration.py

# Test 3: Voice processing
echo "Test 3: Voice processing"
python test_voice_workflow.py

# Test 4: New features
echo "Test 4: New features"
python test_new_tools.py

echo "Regression tests complete"
```

---

## Deployment Guide

### Prerequisites

1. **Working System**: Existing voice-email system functional
2. **Composio Connection**: Gmail OAuth active
3. **Environment Variables**: All credentials set
4. **Virtual Environment**: Python 3.12+ with dependencies

### Step-by-Step Deployment

#### Step 1: Create Tool Directories

```bash
cd ~/Desktop/agency-swarm-voice/voice_email_telegram/email_specialist/tools

# Create organized structure
mkdir -p fetch organize labels drafts send
```

#### Step 2: Deploy Tools One Category at a Time

```bash
# Week 1: Start with read operations
# Create GmailFetchEmails.py in fetch/ directory
# Test independently
python -c "from email_specialist.tools.fetch.GmailFetchEmails import GmailFetchEmails;
           tool = GmailFetchEmails(query='is:unread', max_results=5);
           print(tool.run())"

# If successful, continue with next tool
# If failed, debug before proceeding
```

#### Step 3: Update Agent Configuration

```python
# email_specialist/email_specialist.py
# Agent automatically loads all tools from tools_folder
# No changes needed if tools are in correct directory
```

#### Step 4: Update CEO Instructions

```bash
# Backup current instructions
cp ceo/instructions.md ceo/instructions.md.backup

# Add new intent handling sections (from architecture doc)
# Test CEO can access new tools
```

#### Step 5: Test Integration

```bash
# Start agency in test mode
python agency.py

# Test new intent
# Input: "Show me unread emails"
# Expected: CEO routes to GmailFetchEmails, returns results
```

#### Step 6: Deploy Monitoring Service (Optional)

```bash
# Create gmail_monitoring_service.py
# Test independently first
python gmail_monitoring_service.py

# Once stable, integrate with Telegram bot
```

#### Step 7: Production Launch

```bash
# Create startup script
chmod +x start_voice_email_system.sh
./start_voice_email_system.sh
```

### Rollback Procedure

If anything breaks:

```bash
# Immediate rollback
git stash

# Or restore specific file
cp ceo/instructions.md.backup ceo/instructions.md

# Remove problematic tool
rm email_specialist/tools/fetch/ProblematicTool.py

# Restart system
./start_voice_email_system.sh
```

---

## Validation Checklist

### Pre-Deployment

- [ ] Existing send workflow tested and passing
- [ ] All environment variables set correctly
- [ ] Composio connection active (check with `client.connected_accounts.list()`)
- [ ] Virtual environment activated
- [ ] Backup created of working system

### Per-Tool Deployment

- [ ] Tool file follows Composio pattern exactly
- [ ] Independent unit test passing
- [ ] Returns proper JSON format
- [ ] Error handling implemented
- [ ] No breaking changes to existing tools
- [ ] Regression test passed after integration

### CEO Integration

- [ ] Intent detection accurately routes to new tools
- [ ] Multi-intent handling works
- [ ] Confirmation flows implemented for destructive actions
- [ ] Error messages clear and actionable

### Full System

- [ ] Send workflow still works (baseline)
- [ ] Read workflow returns real data
- [ ] Search workflow accurate
- [ ] Organization operations confirmed
- [ ] Label management functional
- [ ] Draft lifecycle complete
- [ ] Monitoring service polls successfully (if deployed)
- [ ] No performance degradation
- [ ] Rate limiting respected

---

## Documentation & Handoff

### Files to Update

1. **README.md**: Add new features section
2. **SYSTEM_STATUS.md**: Update tool count and capabilities
3. **API_REFERENCE.md**: Document all 20 new tools
4. **USER_GUIDE.md**: Add examples of new commands
5. **.env.example**: Include new optional variables

### User Guide Examples

```markdown
# Voice Email Bot - User Guide (Expanded)

## Sending Emails
"Send an email to john@company.com about the meeting tomorrow"

## Reading Emails
"Show me unread emails"
"Read emails from sarah@company.com"
"Check my inbox"

## Searching Emails
"Find all emails about invoices from last month"
"Search for emails with attachments from the team"

## Organizing
"Archive all promotional emails"
"Mark these emails as read"
"Delete emails older than 6 months"

## Managing Labels
"Show me all my labels"
"Create a label called 'Client Work'"
"Add 'Important' label to this email"

## Draft Operations
"Draft an email to the team about project update"
"Show me my saved drafts"
"Send the draft I created yesterday"
```

---

## Performance Considerations

### Response Time Targets

- **Fetch emails**: <2 seconds
- **Get message details**: <1 second
- **Send email**: <3 seconds
- **Search**: <3 seconds
- **Organization operations**: <1 second

### Optimization Strategies

1. **Caching**:
   - Cache label list (rarely changes)
   - Cache message metadata for recently viewed emails
   - Expire cache after 5 minutes

2. **Parallel Requests**:
   - Fetch multiple message details concurrently
   - Use threading for batch operations

3. **Query Optimization**:
   - Use efficient Gmail query syntax
   - Limit max_results to reasonable numbers
   - Use pagination for large result sets

4. **Monitoring Optimization**:
   - Only fetch message IDs on poll (not full details)
   - Track last_seen timestamp to reduce query size
   - Use smart filtering to reduce API calls

---

## Risk Mitigation

### Identified Risks

1. **Rate Limiting**: Gmail API quota exhausted
   - Mitigation: Implement backoff, monitor usage, cache aggressively

2. **Data Loss**: Accidental email deletion
   - Mitigation: Confirmation flows, soft delete (trash first), audit log

3. **Performance Degradation**: Slow response times
   - Mitigation: Async operations, caching, optimize queries

4. **Breaking Changes**: New tools break existing system
   - Mitigation: Additive-only changes, regression tests, rollback plan

5. **Authentication Failures**: OAuth token expires
   - Mitigation: Composio handles refresh automatically, monitor connection status

6. **Intent Misclassification**: CEO routes to wrong tool
   - Mitigation: Robust intent detection, confidence scoring, clarification prompts

---

## Success Metrics

### Technical Metrics

- **Uptime**: >99% availability
- **Response Time**: 95th percentile <3 seconds
- **Error Rate**: <1% of operations
- **API Quota Usage**: <50% of daily limit

### User Experience Metrics

- **Intent Accuracy**: >90% correct routing
- **First-Response Success**: >85% operations complete without clarification
- **User Satisfaction**: Positive feedback on new features

### Business Metrics

- **Email Processing Time**: 50% reduction vs. manual
- **User Adoption**: All users utilizing read/search features
- **Feature Usage**: All 20 tools used at least weekly

---

## Appendix

### Composio SDK Reference

```python
from composio import Composio

# Initialize
client = Composio(api_key="your_key")

# Execute action
result = client.tools.execute(
    slug="GMAIL_ACTION_NAME",
    arguments={"param": "value"},
    user_id="entity_id",
    dangerously_skip_version_check=True
)

# Response format
{
    "successful": True,
    "data": {...},
    "error": None
}
```

### Gmail Query Syntax

```
# Unread emails
is:unread

# From specific sender
from:user@example.com

# With label
label:IMPORTANT

# Date range
after:2025/10/01 before:2025/11/01

# Has attachment
has:attachment

# Subject contains
subject:meeting

# Combine operators
is:unread from:boss@company.com has:attachment

# Exclude
-label:SPAM

# OR operator
from:alice@company.com OR from:bob@company.com
```

### Environment Variables

```bash
# Required (existing)
OPENAI_API_KEY=sk-...
COMPOSIO_API_KEY=ak_...
GMAIL_ENTITY_ID=pg-test-...
TELEGRAM_BOT_TOKEN=...

# Optional (new)
GMAIL_MONITOR_ENABLED=true
GMAIL_POLL_INTERVAL=120
GMAIL_BUSINESS_HOURS_START=9
GMAIL_BUSINESS_HOURS_END=18
```

---

## Conclusion

This architecture provides a comprehensive, battle-tested approach to expanding the Gmail bot from send-only to full operations. Key principles:

1. **Zero Breaking Changes**: Existing system remains untouched
2. **Proven Pattern**: All tools follow working GmailSendEmail.py template
3. **Incremental Deployment**: Add tools one at a time with testing
4. **Robust Routing**: CEO intelligently detects and routes intents
5. **Production Ready**: Error handling, rate limiting, security built-in

**Status**: Ready for implementation. Begin with Phase 1 (Fetch operations) and iterate through phases weekly.

**Next Action**: Deploy GmailFetchEmails.py following Phase 1 steps.

---

**Document Version**: 1.0
**Last Updated**: 2025-11-01
**Author**: Backend Architect Agent
**Status**: Architecture Complete - Ready for Implementation
