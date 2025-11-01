# GmailSendDraft Quick Reference

## 🚀 One-Liner

```python
from GmailSendDraft import GmailSendDraft
result = GmailSendDraft(draft_id="draft_abc123").run()
```

---

## 📋 Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `draft_id` | str | **Yes** | - | Gmail draft ID to send |
| `user_id` | str | No | `"me"` | Gmail user ID |

---

## 📤 Response

### Success
```json
{
  "success": true,
  "message_id": "msg_18f5a1b2c3d4e5f6",
  "thread_id": "thread_18f5a1b2c3d4e5f6",
  "draft_id": "draft_abc123xyz",
  "message": "Draft sent successfully"
}
```

### Error
```json
{
  "success": false,
  "error": "Draft not found",
  "message_id": null,
  "draft_id": "draft_invalid"
}
```

---

## 🎯 Common Use Cases

### 1. Send Most Recent Draft
```python
from GmailListDrafts import GmailListDrafts
from GmailSendDraft import GmailSendDraft

# List drafts
list_tool = GmailListDrafts(max_results=1)
drafts = json.loads(list_tool.run())

# Send first draft
if drafts.get("drafts"):
    draft_id = drafts["drafts"][0]["id"]
    send_tool = GmailSendDraft(draft_id=draft_id)
    result = send_tool.run()
```

### 2. Review Before Send
```python
from GmailGetDraft import GmailGetDraft
from GmailSendDraft import GmailSendDraft

# Review draft
review = json.loads(GmailGetDraft(draft_id=draft_id).run())
print(f"To: {review['to']}, Subject: {review['subject']}")

# Send after review
if user_approves:
    result = GmailSendDraft(draft_id=draft_id).run()
```

### 3. Voice Command
```python
def handle_voice_send():
    """User says: 'Send that draft'"""
    drafts = json.loads(GmailListDrafts(max_results=1).run())
    if drafts.get("drafts"):
        result = GmailSendDraft(draft_id=drafts["drafts"][0]["id"]).run()
        return "Draft sent" if json.loads(result).get("success") else "Send failed"
```

---

## ⚠️ Error Handling

```python
send_tool = GmailSendDraft(draft_id=draft_id)
result = json.loads(send_tool.run())

if result.get("success"):
    print(f"✓ Sent: {result['message_id']}")
else:
    print(f"✗ Failed: {result.get('error')}")
```

---

## 🔗 Related Tools

| Tool | Purpose |
|------|---------|
| `GmailCreateDraft` | Create drafts → Get draft_id |
| `GmailListDrafts` | List drafts → Find draft_id |
| `GmailGetDraft` | Review draft before sending |
| `GmailSendEmail` | Send email directly (no draft) |

---

## 🧪 Testing

```bash
# Run test suite
cd email_specialist/tools
python test_gmail_send_draft.py

# Quick test
python -c "from GmailSendDraft import GmailSendDraft; print(GmailSendDraft(draft_id='test').run())"
```

---

## 📞 Troubleshooting

| Issue | Solution |
|-------|----------|
| "Missing credentials" | Set `COMPOSIO_API_KEY` and `GMAIL_ENTITY_ID` in `.env` |
| "Draft not found" | Verify draft_id with `GmailListDrafts` |
| "Empty draft_id" | Provide valid draft_id parameter |
| Rate limit errors | Add `time.sleep(1)` between sends |

---

## ✅ Production Checklist

- [ ] `.env` configured with credentials
- [ ] Gmail integration connected in Composio
- [ ] `GMAIL_SEND_DRAFT` action enabled
- [ ] Test suite passing
- [ ] Error handling implemented
- [ ] Logging configured

---

## 📚 Documentation

- **Full Guide**: `GMAIL_SEND_DRAFT_README.md`
- **Integration**: `GMAIL_SEND_DRAFT_INTEGRATION_GUIDE.md`
- **Tests**: `test_gmail_send_draft.py`

---

**Status**: ✅ Production Ready | **Action**: `GMAIL_SEND_DRAFT` | **Version**: 1.0.0
