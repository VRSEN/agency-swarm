# Gmail Composio SDK - Comprehensive Testing Strategy

## Overview

**Purpose**: Validate ALL Gmail Composio SDK actions BEFORE building Agency Swarm tools
**Location**: `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram`
**Test Script**: `test_all_gmail_actions.py`
**Credentials**: Configured in `.env` file

---

## Test Phases (Risk-Based Approach)

### Phase 1: READ-ONLY Actions (SAFE)
**Risk Level**: None - No data modification
**Can rollback**: N/A - No changes made

Actions tested:
- `GMAIL_FETCH_EMAILS` - Retrieve recent emails
- `GMAIL_SEARCH_MESSAGES` - Search with query
- `GMAIL_GET_MESSAGE` - Get specific message details
- `GMAIL_GET_THREAD` - Get email thread
- `GMAIL_LIST_LABELS` - List all labels

**Validation**:
- Actions return expected data structure
- No errors with valid credentials
- Results match Gmail web interface

---

### Phase 2: LABEL & ORGANIZATION Actions (LOW RISK)
**Risk Level**: Low - Changes are easily reversible
**Can rollback**: Yes - Labels can be removed, read/unread toggled

Actions tested:
- `GMAIL_CREATE_LABEL` - Create new label
- `GMAIL_ADD_LABEL` - Add label to message
- `GMAIL_REMOVE_LABEL` - Remove label from message
- `GMAIL_MARK_READ` - Mark message as read
- `GMAIL_MARK_UNREAD` - Mark message as unread

**Validation**:
- Labels appear in Gmail interface
- Messages show correct label assignments
- Read/unread states update correctly
- Test labels can be deleted

**Rollback Strategy**:
1. Delete created test labels via `GMAIL_DELETE_LABEL`
2. Remove labels from messages
3. Restore original read/unread states

---

### Phase 3: DRAFT Actions (MEDIUM RISK)
**Risk Level**: Medium - Creates content but doesn't send
**Can rollback**: Yes - Drafts can be deleted

Actions tested:
- `GMAIL_CREATE_DRAFT` - Create email draft
- `GMAIL_GET_DRAFT` - Retrieve draft details
- `GMAIL_UPDATE_DRAFT` - Update existing draft (if available)
- `GMAIL_DELETE_DRAFT` - Delete draft

**Validation**:
- Drafts appear in Gmail drafts folder
- Draft content matches input
- Drafts are NOT sent automatically
- Drafts can be retrieved and deleted

**Rollback Strategy**:
1. Delete all test drafts via `GMAIL_DELETE_DRAFT`
2. Verify drafts removed from Gmail interface

---

### Phase 4: SEND & MODIFY Actions (HIGH RISK)
**Risk Level**: High - Sends actual emails
**Can rollback**: No - Sent emails cannot be unsent

Actions tested:
- `GMAIL_SEND_EMAIL` - Send email (TO SELF ONLY)
- `GMAIL_REPLY_TO_EMAIL` - Reply to email (TO SELF ONLY)
- `GMAIL_FORWARD_EMAIL` - Forward email (TO SELF ONLY, if available)

**Safety Measures**:
1. All test emails sent to SELF (`info@mtlcraftcocktails.com`)
2. Manual confirmation required before each send
3. Clear subject line: "TEST EMAIL - Composio SDK"
4. Test emails clearly marked as test in body

**Validation**:
- Emails arrive in inbox
- Subject and body content correct
- Reply threads work properly
- No emails sent to external addresses

**Rollback Strategy**:
- Cannot unsend emails
- Manually delete test emails from inbox
- Test emails clearly marked for easy identification

---

## Test Execution Plan

### Pre-Test Checklist

```bash
# 1. Verify credentials
cat .env | grep -E "(COMPOSIO_API_KEY|GMAIL_ENTITY_ID|GMAIL_ACCOUNT)"

# 2. Verify SDK version
pip list | grep composio

# 3. Backup current Gmail state (optional)
# - Note current label count
# - Note inbox unread count
# - Screenshot drafts folder

# 4. Test connectivity
python test_composio_sdk_gmail.py
```

### Running Tests

#### Option 1: Run All Phases (Full Test)
```bash
python test_all_gmail_actions.py
# When prompted, enter: all
```

#### Option 2: Run Safe Tests Only (Phases 1-2)
```bash
python test_all_gmail_actions.py
# When prompted, enter: 1,2
```

#### Option 3: Run Specific Phase
```bash
python test_all_gmail_actions.py
# When prompted, enter: 1  (or 2, 3, 4)
```

### Test Sequence (Recommended)

1. **Start with Phase 1 (Read-Only)**
   ```bash
   python test_all_gmail_actions.py
   # Enter: 1
   ```
   - Validates credentials work
   - Confirms data retrieval
   - Zero risk

2. **Then Phase 2 (Labels)**
   ```bash
   python test_all_gmail_actions.py
   # Enter: 2
   ```
   - Tests organization actions
   - Validates reversibility
   - Low risk

3. **Then Phase 3 (Drafts)**
   ```bash
   python test_all_gmail_actions.py
   # Enter: 3
   ```
   - Tests content creation
   - Confirms no auto-send
   - Medium risk

4. **Finally Phase 4 (Send) - WITH CAUTION**
   ```bash
   python test_all_gmail_actions.py
   # Enter: 4
   ```
   - Only if previous phases pass
   - Requires manual confirmation
   - High risk

---

## Post-Test Validation

### Automated Validation
The test script automatically:
- Generates success/fail report for each action
- Creates JSON report file with detailed results
- Tracks test data for cleanup
- Calculates success rate

### Manual Validation

After tests complete, verify in Gmail web interface:

**Phase 1 (Read-Only)**:
- [ ] No changes to Gmail account
- [ ] No new emails or labels

**Phase 2 (Labels)**:
- [ ] Test labels created (if not cleaned up)
- [ ] Labels can be assigned to messages
- [ ] Read/unread states changed correctly

**Phase 3 (Drafts)**:
- [ ] Test drafts appear in drafts folder
- [ ] Draft content matches test input
- [ ] Drafts NOT sent automatically

**Phase 4 (Send)**:
- [ ] Test emails arrived in inbox
- [ ] Sent to correct address (self)
- [ ] Reply threading works
- [ ] No external emails sent

---

## Expected Results

### Success Criteria

Each action should:
1. **Execute without errors** (status 200 or equivalent)
2. **Return expected data structure** (matches SDK documentation)
3. **Produce visible changes** (for non-read actions)
4. **Match Gmail web interface** (changes appear in UI)

### Known Action Names

Based on standard Gmail API and Composio patterns, expect:

**Read Actions**:
- GMAIL_FETCH_EMAILS
- GMAIL_SEARCH_MESSAGES
- GMAIL_GET_MESSAGE
- GMAIL_GET_THREAD
- GMAIL_LIST_LABELS
- GMAIL_GET_PROFILE
- GMAIL_GET_ATTACHMENT

**Organization Actions**:
- GMAIL_CREATE_LABEL
- GMAIL_UPDATE_LABEL
- GMAIL_DELETE_LABEL
- GMAIL_ADD_LABEL
- GMAIL_REMOVE_LABEL
- GMAIL_MARK_READ
- GMAIL_MARK_UNREAD
- GMAIL_MOVE_TO_TRASH
- GMAIL_ARCHIVE

**Draft Actions**:
- GMAIL_CREATE_DRAFT
- GMAIL_GET_DRAFT
- GMAIL_UPDATE_DRAFT
- GMAIL_DELETE_DRAFT
- GMAIL_LIST_DRAFTS

**Send Actions**:
- GMAIL_SEND_EMAIL (CONFIRMED WORKING)
- GMAIL_REPLY_TO_EMAIL
- GMAIL_FORWARD_EMAIL
- GMAIL_SEND_DRAFT

---

## Handling Failures

### If Phase 1 Fails (Read-Only)
**Likely Causes**:
- Invalid credentials
- Expired OAuth token
- Wrong entity_id or connection_id
- Network issues

**Solutions**:
1. Verify `.env` credentials
2. Re-run `composio login`
3. Check connection status: `composio connections list`
4. Refresh OAuth token if needed

### If Phase 2 Fails (Labels)
**Likely Causes**:
- Insufficient Gmail permissions
- Label already exists
- Message ID invalid

**Solutions**:
1. Check Gmail API scopes
2. Use unique label names
3. Verify message IDs from Phase 1 tests

### If Phase 3 Fails (Drafts)
**Likely Causes**:
- Draft format incorrect
- Missing required fields
- Permission issues

**Solutions**:
1. Verify draft data structure
2. Check all required fields present
3. Test with minimal draft first

### If Phase 4 Fails (Send)
**Likely Causes**:
- Email format invalid
- Recipient address wrong
- Send quota exceeded

**Solutions**:
1. Verify email format (to, subject, body)
2. Confirm recipient is self
3. Check Gmail send limits

---

## Action Priority for Tool Building

Based on Voice Email Telegram Agency needs:

### Critical Actions (Build First)
1. **GMAIL_SEND_EMAIL** - Core functionality (CONFIRMED WORKING)
2. **GMAIL_FETCH_EMAILS** - Monitor inbox
3. **GMAIL_SEARCH_MESSAGES** - Find relevant emails
4. **GMAIL_GET_MESSAGE** - Read email details
5. **GMAIL_CREATE_DRAFT** - Compose emails

### High Priority
6. **GMAIL_REPLY_TO_EMAIL** - Respond to emails
7. **GMAIL_GET_THREAD** - Thread context
8. **GMAIL_MARK_READ** - Organization
9. **GMAIL_ADD_LABEL** - Categorization

### Medium Priority
10. **GMAIL_CREATE_LABEL** - Custom organization
11. **GMAIL_DELETE_DRAFT** - Draft management
12. **GMAIL_GET_PROFILE** - Account info
13. **GMAIL_ARCHIVE** - Inbox management

### Low Priority (Future Enhancement)
14. **GMAIL_FORWARD_EMAIL** - Email forwarding
15. **GMAIL_GET_ATTACHMENT** - Attachment handling
16. **GMAIL_MOVE_TO_TRASH** - Deletion
17. **GMAIL_UPDATE_LABEL** - Label management

---

## Building Agency Swarm Tools

### After Testing Complete

Once all critical actions are validated:

1. **Create Tool Classes**
   ```python
   # Example structure
   class GmailSendTool(BaseTool):
       name = "Gmail Send Email"
       description = "Send email via Gmail using Composio SDK"
       # ... implementation based on test results
   ```

2. **Use Test Results**
   - Copy working action names from test report
   - Use validated parameter formats
   - Include error handling from test failures
   - Document known limitations

3. **Tool Development Order**
   - Start with GMAIL_SEND_EMAIL (already working)
   - Add GMAIL_FETCH_EMAILS
   - Add GMAIL_SEARCH_MESSAGES
   - Add GMAIL_CREATE_DRAFT
   - Continue with high priority actions

4. **Validation Strategy**
   - Each tool tested in isolation
   - Integration tests with multiple tools
   - End-to-end workflow tests
   - Error handling validation

---

## Rollback Procedures

### If Tests Break Production

1. **Immediate Actions**:
   ```bash
   # Stop tests
   Ctrl+C

   # Run cleanup
   python test_all_gmail_actions.py
   # Select cleanup option
   ```

2. **Manual Cleanup**:
   - Delete test labels from Gmail web interface
   - Remove test drafts from drafts folder
   - Delete test emails from inbox
   - Check sent folder for any test emails

3. **Restore OAuth Token**:
   ```bash
   composio logout
   composio login
   # Re-authorize Gmail connection
   ```

4. **Verify Account State**:
   - Check inbox unread count matches pre-test
   - Verify no unexpected labels
   - Confirm drafts folder correct
   - Review sent folder

### Emergency Rollback

If tests cause critical issues:

1. **Disconnect Composio**:
   ```bash
   composio connections delete <connection_id>
   ```

2. **Revoke OAuth Access**:
   - Go to Google Account > Security > Third-party apps
   - Remove Composio access

3. **Re-authorize** (when ready):
   ```bash
   python setup_connections.py
   ```

---

## Validation Checklist (Before Building Tools)

### Pre-Build Validation

- [ ] **All Phase 1 tests pass** (read-only actions work)
- [ ] **Phase 2 tests pass** (organization actions work)
- [ ] **Phase 3 tests pass** (draft actions work)
- [ ] **Phase 4 tests pass** (send actions work - optional but recommended)
- [ ] **Test report generated** with success rates
- [ ] **Manual verification complete** (Gmail web interface checks)
- [ ] **Cleanup successful** (test data removed)
- [ ] **No production impact** (inbox, drafts, labels unchanged)

### Action Availability Confirmation

- [ ] **GMAIL_SEND_EMAIL** - Confirmed working
- [ ] **GMAIL_FETCH_EMAILS** - Tested and validated
- [ ] **GMAIL_SEARCH_MESSAGES** - Tested and validated
- [ ] **GMAIL_GET_MESSAGE** - Tested and validated
- [ ] **GMAIL_CREATE_DRAFT** - Tested and validated
- [ ] **GMAIL_REPLY_TO_EMAIL** - Tested and validated
- [ ] **GMAIL_GET_THREAD** - Tested and validated
- [ ] **GMAIL_ADD_LABEL** - Tested and validated
- [ ] **Other actions** - Documented in test report

### Documentation Ready

- [ ] **Test results saved** (`gmail_test_report_*.json`)
- [ ] **Action names confirmed** (from test output)
- [ ] **Parameter formats documented** (from working tests)
- [ ] **Error patterns identified** (from failed tests)
- [ ] **Known limitations noted** (from test observations)

---

## Success Metrics

### Minimum Viable Testing (MVT)

Before building ANY tools, must have:
- ✅ Phase 1 (Read) - 100% pass rate
- ✅ Phase 2 (Labels) - 80%+ pass rate
- ✅ Phase 3 (Drafts) - 80%+ pass rate
- ⚠️ Phase 4 (Send) - Optional but recommended

### Ideal Testing (Full Validation)

For production-ready tools:
- ✅ Phase 1 (Read) - 100% pass rate
- ✅ Phase 2 (Labels) - 90%+ pass rate
- ✅ Phase 3 (Drafts) - 90%+ pass rate
- ✅ Phase 4 (Send) - 100% pass rate
- ✅ Manual validation complete
- ✅ No production impact
- ✅ Cleanup successful

---

## Next Steps After Testing

1. **Review test report** - Identify all working actions
2. **Document action signatures** - Parameters and return types
3. **Create tool scaffolding** - Based on validated actions
4. **Implement critical tools first** - SEND, FETCH, SEARCH, CREATE_DRAFT
5. **Add error handling** - Based on test failures
6. **Build integration tests** - Multi-tool workflows
7. **Deploy to agency** - Voice Email Telegram Agency integration

---

## Troubleshooting Guide

### Common Issues

**"API Key not provided"**
- Verify `.env` file exists
- Check `COMPOSIO_API_KEY` value
- Try: `export COMPOSIO_API_KEY=your_key`

**"Entity ID not found"**
- Verify `GMAIL_ENTITY_ID` in `.env`
- Check: `composio whoami`
- May need to re-authenticate

**"Connection not found"**
- Verify `GMAIL_CONNECTION_ID` in `.env`
- List connections: `composio connections list`
- Re-connect if needed: `python setup_connections.py`

**"Permission denied"**
- Check Gmail API scopes
- May need to re-authorize OAuth
- Verify account has necessary permissions

**"Rate limit exceeded"**
- Gmail API has rate limits
- Add delays between tests (implemented in script)
- Reduce test scope temporarily

---

## Contact & Support

**Test Script**: `test_all_gmail_actions.py`
**Test Report**: `gmail_test_report_YYYYMMDD_HHMMSS.json`
**Documentation**: This file (`GMAIL_TESTING_STRATEGY.md`)

**Resources**:
- Composio Docs: https://docs.composio.dev
- Gmail API Docs: https://developers.google.com/gmail/api
- Agency Swarm Docs: https://github.com/VRSEN/agency-swarm

---

**Last Updated**: 2025-11-01
**Test Automation Specialist** - Voice Email Telegram Agency
