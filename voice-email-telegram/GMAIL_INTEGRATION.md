# Gmail Integration Guide

Complete guide for integrating Gmail with your voice-first email system using Composio.

---

## Overview

Gmail integration enables your system to:
- Create email drafts
- Read and modify existing drafts
- Send emails
- Search and retrieve emails
- Manage labels and folders
- Handle attachments

---

## Authentication Setup

Gmail uses OAuth 2.0 authentication, which Composio handles automatically. You need to set up a Google Cloud project first.

### Step 1: Create Google Cloud Project

1. **Go to Google Cloud Console**
   - Visit https://console.cloud.google.com
   - Sign in with your Google account

2. **Create New Project**
   - Click project dropdown (top left)
   - Click "New Project"
   - Name: "Voice Email System"
   - Click "Create"
   - Wait for project creation (usually 30 seconds)

3. **Select Your Project**
   - Ensure new project is selected in dropdown

### Step 2: Enable Gmail API

1. **Navigate to APIs & Services**
   - Click hamburger menu (☰)
   - Go to "APIs & Services" > "Library"

2. **Search for Gmail API**
   - Type "Gmail API" in search box
   - Click on "Gmail API" result

3. **Enable the API**
   - Click "Enable" button
   - Wait for API to be enabled

### Step 3: Configure OAuth Consent Screen

1. **Go to OAuth Consent Screen**
   - Navigate to "APIs & Services" > "OAuth consent screen"

2. **Choose User Type**
   - Select **"External"** (for personal Gmail)
   - Select **"Internal"** (if you have Google Workspace)
   - Click "Create"

3. **Fill in App Information**
   - **App name**: Voice Email Assistant
   - **User support email**: Your email
   - **App logo**: (optional)
   - **Application home page**: (optional)
   - **Application privacy policy**: (optional for testing)
   - **Developer contact**: Your email
   - Click "Save and Continue"

4. **Add Scopes**
   - Click "Add or Remove Scopes"
   - Search and select:
     - `https://www.googleapis.com/auth/gmail.compose`
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/gmail.readonly`
   - Click "Update"
   - Click "Save and Continue"

5. **Add Test Users** (for External apps)
   - Click "Add Users"
   - Add your Gmail address
   - Add any other emails that need access
   - Click "Add"
   - Click "Save and Continue"

6. **Review and Submit**
   - Review information
   - Click "Back to Dashboard"

### Step 4: Create OAuth Client ID

1. **Go to Credentials**
   - Navigate to "APIs & Services" > "Credentials"

2. **Create Credentials**
   - Click "Create Credentials"
   - Select "OAuth client ID"

3. **Configure OAuth Client**
   - **Application type**: "Desktop app" (for CLI/local apps)
     - OR "Web application" (for web-hosted apps)
   - **Name**: "Voice Email System Client"

4. **Download Credentials**
   - Click "Create"
   - A dialog shows your Client ID and Client Secret
   - Click "Download JSON" (optional, Composio handles this)
   - Click "OK"

### Step 5: Note Your Credentials

You'll see:
- **Client ID**: Something like `123456789-abc...apps.googleusercontent.com`
- **Client Secret**: Something like `GOCSPX-abc...xyz`

**Important**: You don't need to manually configure these with Composio - it handles the OAuth flow for you.

---

## Connecting Gmail to Composio

### Method 1: Python (Recommended)

```python
from composio import Composio
import os

composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
entity_id = "default_user"

# Initiate Gmail connection (opens browser for OAuth)
connection = composio.connections.initiate(
    integration="GMAIL",
    entity_id=entity_id
)

print(f"Authorize at: {connection.auth_url}")
print("Waiting for authorization...")

# After user authorizes, connection becomes active
# Check status:
import time
max_wait = 300  # 5 minutes
start_time = time.time()

while time.time() - start_time < max_wait:
    conn_status = composio.connections.get(
        integration="GMAIL",
        entity_id=entity_id
    )

    if conn_status.status == "active":
        print("✓ Gmail connected successfully!")
        break

    time.sleep(2)
else:
    print("✗ Authorization timeout")
```

### Method 2: CLI

```bash
# Login to Composio first
composio login

# Add Gmail connection (opens browser)
composio connections add GMAIL --entity-id "default_user"

# Authorize in browser, then return to terminal
```

### Verify Connection

```python
# Check if Gmail is connected
connections = composio.connections.list(entity_id="default_user")

for conn in connections:
    if conn.integration == "GMAIL":
        print(f"Status: {conn.status}")
        print(f"Email: {conn.connection_params.get('email', 'N/A')}")
```

---

## Available Gmail Actions

### Draft Management

#### 1. Create Draft

```python
result = composio.tools.execute(
    action="GMAIL_CREATE_DRAFT",
    params={
        "to": "recipient@example.com",
        "subject": "Project Update",
        "body": "Hi,\n\nHere's the project update...\n\nBest regards",
        "cc": "manager@example.com",  # Optional
        "bcc": "archive@example.com",  # Optional
    },
    entity_id="default_user"
)

draft_id = result['draft']['id']
print(f"Draft created: {draft_id}")
```

#### 2. List Drafts

```python
result = composio.tools.execute(
    action="GMAIL_LIST_DRAFTS",
    params={
        "max_results": 10,  # Optional, default 100
    },
    entity_id="default_user"
)

for draft in result.get('drafts', []):
    print(f"Draft ID: {draft['id']}")
    print(f"Message ID: {draft['message']['id']}")
```

#### 3. Read Draft

```python
result = composio.tools.execute(
    action="GMAIL_READ_DRAFT",
    params={
        "draft_id": "r-1234567890",  # From list_drafts
        "format": "full"  # Options: minimal, full, raw, metadata
    },
    entity_id="default_user"
)

draft = result['draft']
message = draft['message']
payload = message['payload']

# Extract details
subject = next(
    (h['value'] for h in payload['headers'] if h['name'] == 'Subject'),
    'No Subject'
)
to = next(
    (h['value'] for h in payload['headers'] if h['name'] == 'To'),
    ''
)

print(f"Subject: {subject}")
print(f"To: {to}")

# Get body
if 'parts' in payload:
    for part in payload['parts']:
        if part['mimeType'] == 'text/plain':
            import base64
            body = base64.urlsafe_b64decode(part['body']['data']).decode()
            print(f"Body: {body}")
```

#### 4. Update Draft

```python
result = composio.tools.execute(
    action="GMAIL_UPDATE_DRAFT",
    params={
        "draft_id": "r-1234567890",
        "to": "newrecipient@example.com",
        "subject": "Updated: Project Update",
        "body": "Updated email body...",
    },
    entity_id="default_user"
)

print("Draft updated successfully")
```

#### 5. Delete Draft

```python
result = composio.tools.execute(
    action="GMAIL_DELETE_DRAFT",
    params={
        "draft_id": "r-1234567890"
    },
    entity_id="default_user"
)

print("Draft deleted")
```

### Sending Emails

#### 6. Send Email

```python
result = composio.tools.execute(
    action="GMAIL_SEND_EMAIL",
    params={
        "to": "recipient@example.com",
        "subject": "Meeting Reminder",
        "body": "Don't forget our meeting at 3 PM today.",
        "cc": "colleague@example.com",  # Optional
        "bcc": "manager@example.com",   # Optional
    },
    entity_id="default_user"
)

message_id = result['message']['id']
print(f"Email sent: {message_id}")
```

#### 7. Send Draft

```python
result = composio.tools.execute(
    action="GMAIL_SEND_DRAFT",
    params={
        "draft_id": "r-1234567890"
    },
    entity_id="default_user"
)

print(f"Draft sent: {result['message']['id']}")
```

#### 8. Reply to Thread

```python
result = composio.tools.execute(
    action="GMAIL_REPLY_TO_THREAD",
    params={
        "thread_id": "18a1234567890abcd",
        "body": "Thanks for your email. I'll review and get back to you.",
    },
    entity_id="default_user"
)

print("Reply sent")
```

### Reading Emails

#### 9. Fetch Emails

```python
result = composio.tools.execute(
    action="GMAIL_FETCH_EMAILS",
    params={
        "max_results": 10,
        "query": "is:unread",  # Gmail search query
        "include_spam_trash": False
    },
    entity_id="default_user"
)

for message in result.get('messages', []):
    msg_id = message['id']

    # Get full message details
    msg_detail = composio.tools.execute(
        action="GMAIL_GET_MESSAGE",
        params={"message_id": msg_id},
        entity_id="default_user"
    )

    # Extract subject
    headers = msg_detail['message']['payload']['headers']
    subject = next(
        (h['value'] for h in headers if h['name'] == 'Subject'),
        'No Subject'
    )
    print(f"Subject: {subject}")
```

#### 10. Search Emails

```python
# Advanced search queries
queries = [
    "from:john@example.com",
    "subject:invoice",
    "after:2025/01/01",
    "has:attachment",
    "is:unread from:boss@example.com"
]

for query in queries:
    result = composio.tools.execute(
        action="GMAIL_FETCH_EMAILS",
        params={
            "query": query,
            "max_results": 5
        },
        entity_id="default_user"
    )
    print(f"Query '{query}': {len(result.get('messages', []))} results")
```

### Label Management

#### 11. List Labels

```python
result = composio.tools.execute(
    action="GMAIL_LIST_LABELS",
    params={},
    entity_id="default_user"
)

for label in result.get('labels', []):
    print(f"{label['name']} (ID: {label['id']})")
```

#### 12. Create Label

```python
result = composio.tools.execute(
    action="GMAIL_CREATE_LABEL",
    params={
        "name": "Email Drafts Bot",
        "label_list_visibility": "labelShow",
        "message_list_visibility": "show"
    },
    entity_id="default_user"
)

label_id = result['label']['id']
print(f"Label created: {label_id}")
```

#### 13. Apply Label

```python
result = composio.tools.execute(
    action="GMAIL_MODIFY_MESSAGE",
    params={
        "message_id": "18a1234567890abcd",
        "add_label_ids": ["Label_123"],  # Label IDs from list_labels
        "remove_label_ids": []  # Optional
    },
    entity_id="default_user"
)

print("Label applied")
```

---

## Integration with Agency Swarm

### Create Email Agent

```python
from agency_swarm import Agent
from composio import Composio

composio = Composio()
entity_id = "default_user"

# Get Gmail tools
gmail_tools = composio.tools.get(
    toolkits=["GMAIL"],
    entity_id=entity_id
)

# Create agent
email_agent = Agent(
    name="EmailAgent",
    description="Gmail integration agent for email draft management",
    instructions="""
    You are the email management agent for a voice-first email system.

    Your responsibilities:
    1. Create email drafts based on user requests
    2. Read and summarize existing drafts
    3. Update drafts based on user feedback
    4. Send approved drafts
    5. Search and retrieve emails when needed
    6. Manage email labels and organization

    Draft Creation Guidelines:
    - Always include proper greeting
    - Use professional language
    - Format emails clearly
    - Include subject line
    - Sign off appropriately

    Before Sending:
    - Verify recipient email is valid
    - Confirm all required fields are filled
    - Check for attachments if mentioned
    - Get user approval via TelegramAgent

    Error Handling:
    - Verify Gmail connection is active
    - Handle rate limits gracefully
    - Provide clear error messages
    - Suggest alternatives if action fails
    """,
    tools=gmail_tools
)
```

### Draft Workflow Example

```python
class EmailDraftWorkflow:
    def __init__(self, composio, entity_id):
        self.composio = composio
        self.entity_id = entity_id
        self.current_drafts = {}

    def create_draft(self, user_id, recipient, subject, body):
        """Create a new email draft"""
        try:
            result = self.composio.tools.execute(
                action="GMAIL_CREATE_DRAFT",
                params={
                    "to": recipient,
                    "subject": subject,
                    "body": body
                },
                entity_id=self.entity_id
            )

            draft_id = result['draft']['id']
            self.current_drafts[user_id] = draft_id

            return {
                "success": True,
                "draft_id": draft_id,
                "message": "Draft created successfully"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_draft_preview(self, user_id):
        """Get draft for preview"""
        draft_id = self.current_drafts.get(user_id)

        if not draft_id:
            return {"error": "No draft found for user"}

        result = self.composio.tools.execute(
            action="GMAIL_READ_DRAFT",
            params={"draft_id": draft_id},
            entity_id=self.entity_id
        )

        # Parse draft details
        message = result['draft']['message']
        payload = message['payload']
        headers = payload['headers']

        preview = {
            "to": next((h['value'] for h in headers if h['name'] == 'To'), ''),
            "subject": next((h['value'] for h in headers if h['name'] == 'Subject'), ''),
            "body": self._extract_body(payload)
        }

        return preview

    def update_draft(self, user_id, **updates):
        """Update existing draft"""
        draft_id = self.current_drafts.get(user_id)

        if not draft_id:
            return {"error": "No draft found for user"}

        result = self.composio.tools.execute(
            action="GMAIL_UPDATE_DRAFT",
            params={
                "draft_id": draft_id,
                **updates
            },
            entity_id=self.entity_id
        )

        return {"success": True, "message": "Draft updated"}

    def send_draft(self, user_id):
        """Send the approved draft"""
        draft_id = self.current_drafts.get(user_id)

        if not draft_id:
            return {"error": "No draft found for user"}

        result = self.composio.tools.execute(
            action="GMAIL_SEND_DRAFT",
            params={"draft_id": draft_id},
            entity_id=self.entity_id
        )

        # Clean up
        del self.current_drafts[user_id]

        return {
            "success": True,
            "message_id": result['message']['id'],
            "message": "Email sent successfully"
        }

    def delete_draft(self, user_id):
        """Delete draft"""
        draft_id = self.current_drafts.get(user_id)

        if not draft_id:
            return {"error": "No draft found for user"}

        self.composio.tools.execute(
            action="GMAIL_DELETE_DRAFT",
            params={"draft_id": draft_id},
            entity_id=self.entity_id
        )

        del self.current_drafts[user_id]

        return {"success": True, "message": "Draft deleted"}

    def _extract_body(self, payload):
        """Extract email body from payload"""
        import base64

        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    return base64.urlsafe_b64decode(data).decode()
        elif 'body' in payload and 'data' in payload['body']:
            data = payload['body']['data']
            return base64.urlsafe_b64decode(data).decode()

        return ""

# Usage
workflow = EmailDraftWorkflow(composio, "default_user")

# Create draft
result = workflow.create_draft(
    user_id="telegram_123456",
    recipient="john@example.com",
    subject="Meeting Follow-up",
    body="Hi John,\n\nThanks for the meeting today..."
)

# Get preview
preview = workflow.get_draft_preview("telegram_123456")

# Update if needed
workflow.update_draft("telegram_123456", subject="Updated: Meeting Follow-up")

# Send when approved
workflow.send_draft("telegram_123456")
```

---

## Advanced Features

### HTML Emails

```python
html_body = """
<html>
  <body>
    <h1>Project Update</h1>
    <p>Dear Team,</p>
    <ul>
      <li>Task 1: Completed</li>
      <li>Task 2: In Progress</li>
    </ul>
    <p>Best regards,<br>Your Name</p>
  </body>
</html>
"""

result = composio.tools.execute(
    action="GMAIL_CREATE_DRAFT",
    params={
        "to": "team@example.com",
        "subject": "Project Update",
        "body": html_body,
        "html": True  # Indicate HTML content
    },
    entity_id="default_user"
)
```

### Attachments

```python
# Note: Attachment handling may require additional setup
# Check Composio docs for latest attachment API

result = composio.tools.execute(
    action="GMAIL_SEND_EMAIL",
    params={
        "to": "recipient@example.com",
        "subject": "Document Attached",
        "body": "Please find the document attached.",
        "attachments": [
            {
                "filename": "report.pdf",
                "content": base64_encoded_content,
                "mime_type": "application/pdf"
            }
        ]
    },
    entity_id="default_user"
)
```

### Batch Operations

```python
def create_multiple_drafts(drafts_data):
    """Create multiple drafts efficiently"""
    results = []

    for draft_data in drafts_data:
        try:
            result = composio.tools.execute(
                action="GMAIL_CREATE_DRAFT",
                params=draft_data,
                entity_id="default_user"
            )
            results.append({
                "success": True,
                "draft_id": result['draft']['id']
            })
        except Exception as e:
            results.append({
                "success": False,
                "error": str(e)
            })

        time.sleep(0.1)  # Rate limiting

    return results

# Usage
drafts = [
    {"to": "user1@example.com", "subject": "Update", "body": "..."},
    {"to": "user2@example.com", "subject": "Reminder", "body": "..."},
]

results = create_multiple_drafts(drafts)
```

---

## Best Practices

### 1. Error Handling

```python
def safe_gmail_action(action, params):
    """Execute Gmail action with error handling"""
    try:
        result = composio.tools.execute(
            action=action,
            params=params,
            entity_id="default_user"
        )
        return {"success": True, "data": result}

    except Exception as e:
        error_msg = str(e)

        if "quotaExceeded" in error_msg:
            return {"success": False, "error": "Gmail quota exceeded. Try again later."}
        elif "invalidArgument" in error_msg:
            return {"success": False, "error": "Invalid email parameters."}
        elif "notFound" in error_msg:
            return {"success": False, "error": "Draft or message not found."}
        else:
            return {"success": False, "error": f"Gmail error: {error_msg}"}
```

### 2. Email Validation

```python
import re

def validate_email(email):
    """Validate email address"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_draft_params(params):
    """Validate draft parameters"""
    errors = []

    if 'to' not in params or not params['to']:
        errors.append("Recipient email is required")
    elif not validate_email(params['to']):
        errors.append("Invalid recipient email address")

    if 'subject' not in params or not params['subject']:
        errors.append("Subject is required")

    if 'body' not in params or not params['body']:
        errors.append("Email body is required")

    return errors

# Usage
params = {"to": "user@example.com", "subject": "Test", "body": "..."}
errors = validate_draft_params(params)

if errors:
    print("Validation errors:", errors)
else:
    # Create draft
    pass
```

### 3. Rate Limiting

```python
from time import sleep, time
from collections import deque

class GmailRateLimiter:
    def __init__(self, max_requests=100, window=60):
        self.max_requests = max_requests
        self.window = window
        self.requests = deque()

    def wait_if_needed(self):
        """Wait if rate limit reached"""
        now = time()

        # Remove old requests outside window
        while self.requests and self.requests[0] < now - self.window:
            self.requests.popleft()

        if len(self.requests) >= self.max_requests:
            # Wait until oldest request expires
            sleep_time = self.window - (now - self.requests[0])
            if sleep_time > 0:
                print(f"Rate limit reached. Waiting {sleep_time:.1f}s...")
                sleep(sleep_time)

        self.requests.append(now)

# Usage
rate_limiter = GmailRateLimiter(max_requests=10, window=60)

for i in range(20):
    rate_limiter.wait_if_needed()
    # Execute Gmail action
    print(f"Request {i+1}")
```

### 4. Connection Health Check

```python
def check_gmail_connection():
    """Verify Gmail connection is active"""
    try:
        # Try to list labels (lightweight operation)
        result = composio.tools.execute(
            action="GMAIL_LIST_LABELS",
            params={},
            entity_id="default_user"
        )

        return {"healthy": True, "labels_count": len(result.get('labels', []))}

    except Exception as e:
        error_msg = str(e)

        if "invalid_grant" in error_msg:
            return {"healthy": False, "error": "Token expired. Re-authenticate required."}
        elif "unauthorized" in error_msg:
            return {"healthy": False, "error": "Unauthorized. Check connection."}
        else:
            return {"healthy": False, "error": str(e)}

# Periodic health check
import schedule

def periodic_health_check():
    health = check_gmail_connection()
    if not health['healthy']:
        print(f"Gmail connection unhealthy: {health['error']}")
        # Send alert or trigger re-authentication

schedule.every(1).hours.do(periodic_health_check)
```

---

## Troubleshooting

### OAuth Issues

**Problem**: "Access denied" during OAuth
**Solution**:
1. Verify test users are added in OAuth consent screen
2. Check scopes are correctly configured
3. Try incognito/private browser window
4. Clear browser cache and cookies

**Problem**: "Redirect URI mismatch"
**Solution**:
1. Check redirect URIs in OAuth client config
2. Ensure using correct client type (Desktop vs Web)
3. For Composio, let it handle redirect URIs

### API Errors

**Problem**: "Quota exceeded"
**Solution**:
1. Check Gmail API quotas in Google Cloud Console
2. Implement rate limiting
3. Request quota increase if needed

**Problem**: "Invalid argument"
**Solution**:
1. Validate email addresses
2. Check required parameters are provided
3. Verify data types match API expectations

### Connection Issues

**Problem**: Connection shows "inactive"
**Solution**:
```python
# Refresh connection
composio.connections.refresh(
    integration="GMAIL",
    entity_id="default_user"
)
```

**Problem**: Tokens expired
**Solution**:
```python
# Re-initiate connection
composio.connections.delete(
    integration="GMAIL",
    entity_id="default_user"
)

composio.connections.initiate(
    integration="GMAIL",
    entity_id="default_user"
)
```

---

## MCP Server Alternative

If you prefer MCP servers over Composio:

```bash
# Install Gmail MCP server
npm install gmail-mcp-server

# Or use specific implementation
git clone https://github.com/GongRzhe/Gmail-MCP-Server
cd Gmail-MCP-Server
npm install
```

Configure in `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "gmail": {
      "command": "node",
      "args": ["/path/to/gmail-mcp-server/build/index.js"],
      "env": {
        "GMAIL_CREDENTIALS_PATH": "/path/to/credentials.json"
      }
    }
  }
}
```

---

## Security Best Practices

1. **Never expose credentials**
   ```python
   # Use environment variables
   credentials = os.getenv("GMAIL_CREDENTIALS")
   ```

2. **Minimize OAuth scopes**
   - Only request scopes you need
   - Avoid `gmail.full` if possible

3. **Implement user consent**
   ```python
   # Always confirm before sending
   def send_with_confirmation(draft_preview):
       print("Draft preview:")
       print(draft_preview)
       confirm = input("Send this email? (yes/no): ")
       return confirm.lower() == "yes"
   ```

4. **Audit email access**
   - Log all email operations
   - Monitor for unusual activity
   - Implement alerts for bulk operations

---

## Resources

- Gmail API Docs: https://developers.google.com/gmail/api
- OAuth 2.0 Guide: https://developers.google.com/identity/protocols/oauth2
- Composio Gmail: https://docs.composio.dev/toolkits/gmail
- Gmail Search Operators: https://support.google.com/mail/answer/7190

---

## Next Steps

1. Complete Google Cloud setup
2. Test OAuth flow with Composio
3. Implement draft creation
4. Add approval workflow
5. Integrate with Telegram and voice agents
