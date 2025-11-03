# Gmail Composio REST API Integration - FIXED

**Date**: November 1, 2025
**Status**: ✅ **WORKING** - GmailFetchEmails.py successfully fetching emails via Composio REST API
**Impact**: Unblocks Telegram bot Gmail integration

---

## Problem Summary

### Root Cause
The Composio SDK (both v0.9.0 and v1.0.0-rc2) is broken - returns 404 for Gmail tools. However, the Composio REST API works correctly.

### Solution
Convert Gmail tools from SDK to direct REST API calls.

---

## Technical Fix Details

### Issue 1: Wrong Connection ID Format
**Problem**: Was using `ca_xqTpxi5vweu_` (short format from dashboard UI)
**Fix**: Use full UUID from `/api/v1/connectedAccounts` endpoint
**Correct ID**: `52b8bf1d-b0e9-4c94-bf2d-e41d2fca4183`

### Issue 2: Connection ID Must Match Entity ID
**Problem**: Multiple Gmail connections exist, must use one matching current entity
**Entity ID**: `pg-test-12561871-7684-4ba1-ae78-e14dcd9a16d3`
**Connection ID**: `52b8bf1d-b0e9-4c94-bf2d-e41d2fca4183` (created 2025-11-02T03:17:34.733Z)

### Updated .env Configuration
```bash
# Gmail Connection via Composio - AUTO-CONFIGURED
# Updated 2025-11-01: Using most recent connection for entity pg-test-12561871-7684-4ba1-ae78-e14dcd9a16d3
GMAIL_CONNECTION_ID=52b8bf1d-b0e9-4c94-bf2d-e41d2fca4183
GMAIL_ENTITY_ID=pg-test-12561871-7684-4ba1-ae78-e14dcd9a16d3
GMAIL_ACCOUNT=info@mtlcraftcocktails.com
```

---

## REST API Pattern (Working)

### Request Structure
```python
url = "https://backend.composio.dev/api/v2/actions/GMAIL_FETCH_EMAILS/execute"
headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}
payload = {
    "connectedAccountId": connection_id,  # Must be full UUID, not ca_* format
    "input": {
        "query": self.query,
        "max_results": self.max_results,
        "user_id": "me",
        "include_payload": True,
        "verbose": True
    }
}

response = requests.post(url, headers=headers, json=payload, timeout=30)
```

### Response Format
```json
{
  "data": {
    "messages": [
      {
        "messageId": "19a4215f0a940d73",
        "threadId": "19a4215f0a940d73",
        "sender": "info@mtlcraftcocktails.com",
        "to": "ash.cocktails@gmail.com",
        "subject": "Receipt Processed Successfully",
        "messageText": "...",
        "messageTimestamp": "2025-11-02T01:02:04Z",
        "labelIds": ["SENT"],
        "attachmentList": [],
        "payload": { ... }
      }
    ]
  }
}
```

---

## Test Results

### ✅ Successfully Tested
```bash
python email_specialist/tools/GmailFetchEmails.py
```

**Result**: Status 200, successfully fetched multiple emails from info@mtlcraftcocktails.com inbox.

**Sample Email Retrieved**:
- Subject: "Receipt Processed Successfully"
- From: info@mtlcraftcocktails.com
- To: ash.cocktails@gmail.com
- Timestamp: 2025-11-02T01:02:04Z
- Labels: SENT

---

## Updated Tool Implementation

### File: `/email_specialist/tools/GmailFetchEmails.py`

**Key Changes**:
1. Line 10: Added `import requests` for direct REST API calls
2. Line 68: Uses `GMAIL_CONNECTION_ID` (not `GMAIL_ENTITY_ID`)
3. Lines 89-103: Direct REST API request instead of SDK
4. Lines 106-129: Handle Composio REST API response format

**Working Code Snippet**:
```python
# Get Composio credentials
api_key = os.getenv("COMPOSIO_API_KEY")
entity_id = os.getenv("GMAIL_CONNECTION_ID")  # Use connection ID (ca_*) not entity ID

# Prepare API request
url = "https://backend.composio.dev/api/v2/actions/GMAIL_FETCH_EMAILS/execute"
headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}
payload = {
    "connectedAccountId": entity_id,
    "input": {
        "query": self.query,
        "max_results": self.max_results,
        "user_id": "me",
        "include_payload": True,
        "verbose": True
    }
}

# Execute via Composio REST API
response = requests.post(url, headers=headers, json=payload, timeout=30)
response.raise_for_status()

result = response.json()

# Extract messages from response
if result.get("successfull") or result.get("data"):
    messages = result.get("data", {}).get("messages", [])
    return json.dumps({
        "success": True,
        "count": len(messages),
        "messages": messages,
        "query": self.query if self.query else "all recent emails",
        "max_results": self.max_results
    }, indent=2)
```

---

## Next Steps: Replicate Pattern to 24 Remaining Gmail Tools

### Tools to Update (Same Pattern)
1. GmailGetMessage.py
2. GmailListThreads.py
3. GmailBatchModifyMessages.py
4. GmailAddLabel.py
5. GmailMoveToTrash.py
6. GmailCreateDraft.py
7. GmailListDrafts.py
8. GmailSendDraft.py
9. GmailDeleteDraft.py
10. GmailGetAttachment.py
11. GmailListLabels.py
12. GmailCreateLabel.py
13. GmailRemoveLabel.py
14. GmailSendEmail.py
15. GmailGetProfile.py
16. GmailSearchPeople.py
17. GmailGetContacts.py
18. GmailPatchLabel.py
19. GmailFetchMessageByThreadId.py
20. GmailBatchDeleteMessages.py
21. GmailModifyThreadLabels.py
22. (4 more tools...)

### Conversion Template

**Find**:
```python
from composio import Composio

composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))
entity_id = os.getenv("GMAIL_ENTITY_ID")

result = composio.execute_action(
    action="GMAIL_ACTION_NAME",
    params={...},
    entity_id=entity_id
)
```

**Replace with**:
```python
import requests

api_key = os.getenv("COMPOSIO_API_KEY")
connection_id = os.getenv("GMAIL_CONNECTION_ID")

url = "https://backend.composio.dev/api/v2/actions/GMAIL_ACTION_NAME/execute"
headers = {
    "X-API-Key": api_key,
    "Content-Type": "application/json"
}
payload = {
    "connectedAccountId": connection_id,
    "input": {...}
}

response = requests.post(url, headers=headers, json=payload, timeout=30)
response.raise_for_status()
result = response.json()
```

---

## How to Find Correct Connection ID for Any Entity

```bash
# Get all connected accounts
curl -X GET 'https://backend.composio.dev/api/v1/connectedAccounts' \
  -H 'X-API-Key: YOUR_API_KEY'

# Filter by entity and app:
# 1. Look for "clientUniqueUserId": "YOUR_ENTITY_ID"
# 2. Check "appUniqueId": "gmail"
# 3. Use "id" field (full UUID format)
```

**Python Helper**:
```python
import requests
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('COMPOSIO_API_KEY')
entity_id = os.getenv('GMAIL_ENTITY_ID')

response = requests.get(
    'https://backend.composio.dev/api/v1/connectedAccounts',
    headers={'X-API-Key': api_key}
)

connections = response.json()['items']
gmail_connections = [
    c for c in connections
    if c['appUniqueId'] == 'gmail' and c['clientUniqueUserId'] == entity_id
]

for conn in gmail_connections:
    print(f"ID: {conn['id']}")
    print(f"Status: {conn['status']}")
    print(f"Created: {conn['createdAt']}")
```

---

## Verification Commands

### Test Single Tool
```bash
python email_specialist/tools/GmailFetchEmails.py
```

### Test All Gmail Tools (Once Converted)
```bash
python test_all_gmail_actions.py
```

### Check Connection Status
```bash
python check_composio_connections.py
```

---

## Key Learnings

1. **Connection ID Format**: Dashboard shows short `ca_*` format, but API requires full UUID
2. **Entity Matching**: Connection ID must match entity ID, not just any active connection
3. **Multiple Connections**: User may have multiple Gmail connections - use most recent for correct entity
4. **SDK vs REST**: Composio SDK is broken, REST API works reliably
5. **Error Messages**: "Invalid uuid" means wrong ID format; "Unauthorized" means wrong entity

---

## Status: Ready for Mass Conversion

**Template Verified**: ✅
**Connection Verified**: ✅
**API Response Validated**: ✅
**Ready to Convert**: 24 remaining Gmail tools

**Estimated Time**: ~2-3 hours to convert all 24 tools using search/replace pattern

---

*Fixed by: backend-architect agent*
*Date: November 1, 2025*
*Working Directory: /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram*
