# GmailGetProfile Tool

**Gmail User Profile Information Retrieval Tool**

Gets comprehensive Gmail user profile information including email address, message count, thread count, and mailbox statistics using the Composio SDK.

## Overview

- **Action**: `GMAIL_GET_PROFILE`
- **Purpose**: Retrieve Gmail user profile and mailbox statistics
- **Pattern**: Validated Composio SDK implementation
- **Status**: Production-ready

## Features

- ✅ Get primary Gmail email address
- ✅ Total message count
- ✅ Total thread count
- ✅ History ID for change tracking
- ✅ Messages per thread ratio calculation
- ✅ Mailbox health assessment
- ✅ Comprehensive error handling
- ✅ JSON formatted output

## Installation

### Prerequisites

```bash
# Install required packages
pip install composio-core agency-swarm python-dotenv pydantic

# Set up environment variables in .env
COMPOSIO_API_KEY=your_composio_api_key
GMAIL_ENTITY_ID=your_gmail_entity_id
```

### Setup

1. **Connect Gmail Account via Composio**:
   ```bash
   composio add gmail
   ```

2. **Get Entity ID**:
   ```bash
   composio connections list
   ```

3. **Configure Environment**:
   ```bash
   echo "COMPOSIO_API_KEY=your_key" >> .env
   echo "GMAIL_ENTITY_ID=your_entity" >> .env
   ```

## Usage

### Basic Usage

```python
from email_specialist.tools.GmailGetProfile import GmailGetProfile

# Get profile for authenticated user
tool = GmailGetProfile()
result = tool.run()
print(result)
```

### Example Output

```json
{
  "success": true,
  "email_address": "user@gmail.com",
  "messages_total": 15234,
  "threads_total": 8942,
  "history_id": "1234567890",
  "messages_per_thread": 1.70,
  "profile_summary": "user@gmail.com has 15234 messages in 8942 threads",
  "user_id": "me"
}
```

### Use Cases

#### 1. **Check Gmail Address**
```python
# "What's my Gmail address?"
tool = GmailGetProfile()
result = json.loads(tool.run())

if result["success"]:
    print(f"Your Gmail: {result['email_address']}")
```

#### 2. **Get Message Count**
```python
# "How many emails do I have?"
tool = GmailGetProfile()
result = json.loads(tool.run())

if result["success"]:
    messages = result["messages_total"]
    threads = result["threads_total"]
    print(f"You have {messages:,} messages in {threads:,} threads")
```

#### 3. **Show Full Profile**
```python
# "Show my Gmail profile"
tool = GmailGetProfile()
result = json.loads(tool.run())

if result["success"]:
    print(f"Email: {result['email_address']}")
    print(f"Messages: {result['messages_total']:,}")
    print(f"Threads: {result['threads_total']:,}")
    print(f"Ratio: {result['messages_per_thread']}")
```

#### 4. **Mailbox Health Check**
```python
# System status monitoring
tool = GmailGetProfile()
result = json.loads(tool.run())

if result["success"]:
    ratio = result["messages_per_thread"]

    if ratio < 2:
        health = "Healthy - Most emails standalone"
    elif ratio < 5:
        health = "Normal - Moderate activity"
    elif ratio < 10:
        health = "Active - High engagement"
    else:
        health = "Very Active - Extensive threads"

    print(f"Mailbox Health: {health}")
```

#### 5. **Quota Monitoring**
```python
# Check mailbox statistics for quota planning
tool = GmailGetProfile()
result = json.loads(tool.run())

if result["success"]:
    total = result["messages_total"]
    # Gmail free tier limit: ~15GB or ~15,000 messages
    if total > 12000:
        print("⚠️ Approaching storage limits")
    else:
        print(f"✓ Storage healthy: {total:,} messages")
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `user_id` | str | `"me"` | Gmail user ID (use "me" for authenticated user) |

## Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | Whether profile fetch succeeded |
| `email_address` | str | Primary Gmail email address |
| `messages_total` | int | Total number of messages in mailbox |
| `threads_total` | int | Total number of conversation threads |
| `history_id` | str | Mailbox history identifier for tracking changes |
| `messages_per_thread` | float | Average messages per thread (rounded to 2 decimals) |
| `profile_summary` | str | Human-readable profile summary |
| `user_id` | str | Gmail user ID used for query |
| `error` | str | Error message (only present if success=false) |
| `type` | str | Error type (only present if exception occurred) |

## Error Handling

### Missing Credentials
```json
{
  "success": false,
  "error": "Missing Composio credentials. Set COMPOSIO_API_KEY and GMAIL_ENTITY_ID in .env",
  "email_address": null,
  "messages_total": 0,
  "threads_total": 0
}
```

### API Error
```json
{
  "success": false,
  "error": "Error fetching Gmail profile: <error details>",
  "type": "ComposioAPIError",
  "email_address": null,
  "messages_total": 0,
  "threads_total": 0,
  "user_id": "me"
}
```

## Testing

### Run Built-in Tests
```bash
# Run standalone tool tests
python GmailGetProfile.py

# Run comprehensive test suite
python test_gmail_get_profile.py
```

### Test Coverage
- ✅ Default user profile retrieval
- ✅ Explicit user_id parameter
- ✅ Profile data structure validation
- ✅ Mailbox statistics calculation
- ✅ Missing credentials handling
- ✅ Profile summary formatting
- ✅ JSON output format validation
- ✅ Zero threads edge case

## Integration Examples

### With Agency Swarm Agent

```python
from agency_swarm import Agent
from email_specialist.tools.GmailGetProfile import GmailGetProfile

email_agent = Agent(
    name="Email Specialist",
    description="Handles Gmail operations",
    tools=[GmailGetProfile],
    temperature=0.5
)

# Agent can now respond to:
# - "What's my Gmail address?"
# - "How many emails do I have?"
# - "Show my Gmail profile"
```

### Voice Assistant Integration

```python
def handle_voice_command(command: str):
    """Process voice commands related to Gmail profile"""

    if "gmail address" in command.lower():
        tool = GmailGetProfile()
        result = json.loads(tool.run())
        if result["success"]:
            return f"Your Gmail address is {result['email_address']}"

    elif "how many emails" in command.lower():
        tool = GmailGetProfile()
        result = json.loads(tool.run())
        if result["success"]:
            count = result["messages_total"]
            return f"You have {count:,} emails"

    elif "gmail profile" in command.lower():
        tool = GmailGetProfile()
        result = json.loads(tool.run())
        if result["success"]:
            return result["profile_summary"]
```

### Dashboard Integration

```python
import streamlit as st

def display_gmail_profile():
    """Display Gmail profile in dashboard"""

    tool = GmailGetProfile()
    result = json.loads(tool.run())

    if result["success"]:
        st.header("📧 Gmail Profile")
        st.metric("Email Address", result["email_address"])
        st.metric("Total Messages", f"{result['messages_total']:,}")
        st.metric("Total Threads", f"{result['threads_total']:,}")
        st.metric("Messages per Thread", result["messages_per_thread"])

        # Display mailbox health
        ratio = result["messages_per_thread"]
        if ratio < 5:
            st.success("✓ Mailbox Healthy")
        elif ratio < 10:
            st.info("ℹ️ Active Mailbox")
        else:
            st.warning("⚠️ Very Active Threads")
```

## Performance

- **Average Response Time**: 200-500ms
- **Rate Limits**: Subject to Gmail API quotas (1,000,000,000 quota units/day)
- **Caching**: Consider caching profile data (TTL: 5-10 minutes)
- **Cost**: Free tier available through Composio

## Best Practices

1. **Cache Profile Data**: Profile info rarely changes, cache for 5-10 minutes
2. **Handle Errors Gracefully**: Always check `success` field before using data
3. **Monitor Rate Limits**: Track API usage to avoid quota exhaustion
4. **Use for Status Checks**: Ideal for system health monitoring
5. **Combine with Other Tools**: Use alongside GmailFetchEmails for complete solution

## Troubleshooting

### Issue: "Missing Composio credentials"
**Solution**: Ensure `.env` file contains:
```bash
COMPOSIO_API_KEY=your_key
GMAIL_ENTITY_ID=your_entity
```

### Issue: Profile returns zero messages
**Solution**:
- Verify Gmail account is properly connected via Composio
- Check account permissions/scopes include Gmail read access
- Ensure entity_id matches connected account

### Issue: Slow response times
**Solution**:
- Implement caching for profile data
- Use Redis or in-memory cache with 5-10 minute TTL
- Monitor Composio API health status

## Related Tools

- **GmailFetchEmails**: Fetch and search emails
- **GmailListLabels**: List available Gmail labels
- **GmailSendEmail**: Send emails programmatically
- **GmailModifyThreadLabels**: Organize email threads

## API Reference

### Composio Action
```
Action: GMAIL_GET_PROFILE
Method: users.getProfile
Scope: https://www.googleapis.com/auth/gmail.readonly
```

### Gmail API Documentation
- [Gmail API - Users.getProfile](https://developers.google.com/gmail/api/reference/rest/v1/users/getProfile)
- [Composio Gmail Integration](https://docs.composio.dev/integrations/gmail)

## Support

- **Documentation**: `/email_specialist/tools/GmailGetProfile_README.md`
- **Tests**: `test_gmail_get_profile.py`
- **Pattern Reference**: `FINAL_VALIDATION_SUMMARY.md`

## Version History

- **v1.0.0** (2025-01-01): Initial release
  - Profile retrieval with message/thread counts
  - Mailbox statistics calculation
  - Comprehensive error handling
  - Full test coverage

## License

MIT License - See project LICENSE file for details
