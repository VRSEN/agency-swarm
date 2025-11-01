# Quick Test Guide - Gmail Composio SDK Actions

## 5-Minute Quick Start

### 1. Verify Setup (30 seconds)

```bash
cd /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram

# Check credentials
cat .env | grep -E "(COMPOSIO_API_KEY|GMAIL_ENTITY_ID|GMAIL_ACCOUNT)"

# Should show:
# COMPOSIO_API_KEY=ak_suouXXwN2bd7UvBbjJvu
# GMAIL_ENTITY_ID=pg-test-5fef8fe8-9810-4900-8ebf-9de6c1057220
# GMAIL_ACCOUNT=info@mtlcraftcocktails.com
```

### 2. Run Safe Tests First (2 minutes)

```bash
# Test read-only actions (100% safe, no modifications)
python test_all_gmail_actions.py

# When prompted:
# Phases (default: all): 1

# Expected output:
# ✅ GMAIL_FETCH_EMAILS [PASS]
# ✅ GMAIL_SEARCH_MESSAGES [PASS]
# ✅ GMAIL_GET_MESSAGE [PASS]
# ✅ GMAIL_GET_THREAD [PASS]
# ✅ GMAIL_LIST_LABELS [PASS]
```

### 3. Test Organization Actions (2 minutes)

```bash
# Test label and read/unread actions (low risk)
python test_all_gmail_actions.py

# When prompted:
# Phases (default: all): 2

# Expected output:
# ✅ GMAIL_CREATE_LABEL [PASS]
# ✅ GMAIL_ADD_LABEL [PASS]
# ✅ GMAIL_REMOVE_LABEL [PASS]
# ✅ GMAIL_MARK_READ [PASS]
# ✅ GMAIL_MARK_UNREAD [PASS]
```

### 4. Test Drafts (1 minute)

```bash
# Test draft creation (medium risk, no send)
python test_all_gmail_actions.py

# When prompted:
# Phases (default: all): 3

# Expected output:
# ✅ GMAIL_CREATE_DRAFT [PASS]
# ✅ GMAIL_GET_DRAFT [PASS]

# IMPORTANT: Check Gmail drafts folder to verify!
```

### 5. Review Results (30 seconds)

```bash
# Check test report
ls -lt gmail_test_report_*.json | head -1

# View summary
cat gmail_test_report_*.json | python -m json.tool | grep -A 10 "summary"
```

---

## What Each Phase Tests

### Phase 1: Read-Only (SAFE)
- 🔍 Fetches emails from inbox
- 🔍 Searches for specific emails
- 🔍 Gets message details
- 🔍 Gets email threads
- 🔍 Lists all labels

**Risk**: NONE - Only reads data

---

### Phase 2: Organization (LOW RISK)
- 🏷️ Creates test labels
- 🏷️ Adds labels to messages
- 🏷️ Removes labels from messages
- ✉️ Marks messages as read
- ✉️ Marks messages as unread

**Risk**: LOW - All changes reversible

---

### Phase 3: Drafts (MEDIUM RISK)
- 📝 Creates email drafts
- 📝 Retrieves draft details

**Risk**: MEDIUM - Creates content but doesn't send

---

### Phase 4: Send (HIGH RISK) - OPTIONAL
- 📧 Sends email to SELF
- 📧 Replies to email

**Risk**: HIGH - Sends actual emails (to yourself only)

---

## Expected Output

### Successful Test Run

```
================================================================================
PHASE 1: READ-ONLY ACTIONS (SAFE)
================================================================================

🔄 GMAIL_FETCH_EMAILS - Fetch recent emails [TESTING]
✅ GMAIL_FETCH_EMAILS [PASS]
   Retrieved: 5 emails

🔄 GMAIL_SEARCH_MESSAGES - Search emails [TESTING]
✅ GMAIL_SEARCH_MESSAGES [PASS]
   Found: 3 unread emails

...

================================================================================
TEST RESULTS SUMMARY
================================================================================

PHASE 1 READ ONLY:
  ✅ PASS - fetch_emails
  ✅ PASS - search_messages
  ✅ PASS - get_message
  ✅ PASS - get_thread
  ✅ PASS - list_labels

================================================================================
TOTAL: 5 tests
✅ PASSED: 5
❌ FAILED: 0
⏭️  SKIPPED: 0
Success Rate: 100.0%
================================================================================

📄 Detailed report saved to: gmail_test_report_20251101_143022.json
```

---

## Troubleshooting

### Error: "API Key not provided"

```bash
# Solution 1: Check .env file
cat .env | grep COMPOSIO_API_KEY

# Solution 2: Export manually
export COMPOSIO_API_KEY=ak_suouXXwN2bd7UvBbjJvu
```

### Error: "Entity ID not found"

```bash
# Check entity ID
cat .env | grep GMAIL_ENTITY_ID

# Verify with Composio
composio whoami
```

### Error: "Connection not found"

```bash
# List connections
composio connections list

# Should show Gmail connection with ID: 0d6c0e2d-7fd8-4700-89c0-17a871ae03da

# If missing, reconnect:
python setup_connections.py
```

### Tests Fail or Skip

**Common reasons**:
1. No emails in inbox (fetch/search will skip)
2. No unread emails (mark_read will skip)
3. Permissions missing (check Gmail API scopes)

**Solutions**:
- Send yourself a test email first
- Mark some emails as unread
- Re-authorize Gmail connection

---

## Quick Decision Matrix

| Phase 1 Result | Phase 2 Result | Decision |
|---------------|---------------|----------|
| 100% pass | Any | ✅ **Proceed** - Core functionality works |
| 80%+ pass | 80%+ pass | ⚠️ **Conditional** - Build with limitations |
| <80% pass | Any | ❌ **Stop** - Fix issues first |

---

## Next Steps After Testing

### If All Tests Pass ✅

1. Review test report: `cat gmail_test_report_*.json`
2. Fill out validation checklist: `VALIDATION_CHECKLIST.md`
3. Start building Agency Swarm tools
4. Begin with GmailSendTool (already confirmed working)

### If Some Tests Fail ⚠️

1. Check error messages in test output
2. Investigate specific action failures
3. Document limitations
4. Build tools only for working actions
5. Plan to enhance as issues are resolved

### If Most Tests Fail ❌

1. Verify credentials in `.env`
2. Check Gmail connection: `composio connections list`
3. Re-authorize if needed: `python setup_connections.py`
4. Check Gmail API permissions
5. Review error logs for patterns

---

## Time Estimates

| Phase | Time | Risk | Required |
|-------|------|------|----------|
| Phase 1 | 2 min | None | YES |
| Phase 2 | 2 min | Low | YES |
| Phase 3 | 1 min | Medium | Recommended |
| Phase 4 | 2 min | High | Optional |
| **Total** | **7 min** | - | - |

**Minimum Testing**: Phases 1-2 only (4 minutes)
**Recommended Testing**: Phases 1-3 (5 minutes)
**Full Testing**: All phases (7 minutes)

---

## Command Reference

### Run Specific Phase
```bash
python test_all_gmail_actions.py
# Enter phase number when prompted: 1, 2, 3, or 4
```

### Run Multiple Phases
```bash
python test_all_gmail_actions.py
# Enter comma-separated: 1,2,3
```

### Run All Phases
```bash
python test_all_gmail_actions.py
# Just press Enter (defaults to all)
```

### Skip Cleanup
```bash
python test_all_gmail_actions.py
# When asked to clean up, enter: no
# (Useful for inspecting test labels/drafts in Gmail)
```

---

## Test Report Location

After each test run, a report is saved:

```
/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/gmail_test_report_YYYYMMDD_HHMMSS.json
```

**Report contains**:
- Success/fail status for each action
- Error messages for failures
- Test data created (labels, drafts, sent messages)
- Timestamps for each test
- Overall success rate

---

## Safety Features Built-In

✅ **Test emails only sent to self** (info@mtlcraftcocktails.com)
✅ **Manual confirmation required** for send actions
✅ **Clear test labels** in subject lines
✅ **Automatic cleanup** of test data
✅ **Phase-based execution** (run only what you need)
✅ **Detailed error logging** for troubleshooting
✅ **Reversible actions** in Phases 1-3

---

## Questions?

**See full documentation**: `GMAIL_TESTING_STRATEGY.md`
**See validation checklist**: `VALIDATION_CHECKLIST.md`
**Original working test**: `test_composio_sdk_gmail.py`

---

**Last Updated**: 2025-11-01
**Quick Test Guide Version**: 1.0
