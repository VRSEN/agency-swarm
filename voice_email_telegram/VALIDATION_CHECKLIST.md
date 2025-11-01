# Gmail Composio SDK - Pre-Tool-Build Validation Checklist

## Quick Reference Checklist

Use this checklist BEFORE building any Agency Swarm tools.

---

## Pre-Test Setup

- [ ] Environment variables configured (`.env` file)
  - [ ] COMPOSIO_API_KEY
  - [ ] GMAIL_ENTITY_ID
  - [ ] GMAIL_CONNECTION_ID
  - [ ] GMAIL_ACCOUNT

- [ ] Composio SDK installed (`pip list | grep composio`)

- [ ] Gmail connection active (`composio connections list`)

- [ ] Existing test passes (`python test_composio_sdk_gmail.py`)

---

## Phase 1: Read-Only Actions (MUST PASS)

Run: `python test_all_gmail_actions.py` → Enter: `1`

- [ ] GMAIL_FETCH_EMAILS - Retrieves recent emails
- [ ] GMAIL_SEARCH_MESSAGES - Searches with query
- [ ] GMAIL_GET_MESSAGE - Gets message details
- [ ] GMAIL_GET_THREAD - Gets email thread
- [ ] GMAIL_LIST_LABELS - Lists all labels

**Result**: _____ / 5 passed

**Status**:
- [ ] ✅ All pass (100%) - PROCEED to Phase 2
- [ ] ⚠️ Some fail - INVESTIGATE before proceeding
- [ ] ❌ All fail - CHECK credentials/connection

---

## Phase 2: Label & Organization (SHOULD PASS)

Run: `python test_all_gmail_actions.py` → Enter: `2`

- [ ] GMAIL_CREATE_LABEL - Creates test label
- [ ] GMAIL_ADD_LABEL - Adds label to message
- [ ] GMAIL_REMOVE_LABEL - Removes label from message
- [ ] GMAIL_MARK_READ - Marks message as read
- [ ] GMAIL_MARK_UNREAD - Marks message as unread

**Result**: _____ / 5 passed

**Manual Verification**:
- [ ] Test label visible in Gmail web interface
- [ ] Message shows label in Gmail
- [ ] Read/unread state changes in Gmail

**Status**:
- [ ] ✅ 4+ pass (80%+) - PROCEED to Phase 3
- [ ] ⚠️ 2-3 pass - PARTIAL support, document limitations
- [ ] ❌ 0-1 pass - CHECK permissions

---

## Phase 3: Draft Actions (SHOULD PASS)

Run: `python test_all_gmail_actions.py` → Enter: `3`

- [ ] GMAIL_CREATE_DRAFT - Creates email draft
- [ ] GMAIL_GET_DRAFT - Retrieves draft details

**Result**: _____ / 2 passed

**Manual Verification**:
- [ ] Draft appears in Gmail drafts folder
- [ ] Draft content matches test input
- [ ] Draft is NOT sent (remains in drafts)

**Status**:
- [ ] ✅ All pass (100%) - PROCEED to Phase 4
- [ ] ⚠️ Partial - DOCUMENT limitations
- [ ] ❌ All fail - CHECK draft permissions

---

## Phase 4: Send Actions (OPTIONAL BUT RECOMMENDED)

Run: `python test_all_gmail_actions.py` → Enter: `4`

⚠️ **WARNING**: This sends real emails (to yourself)

- [ ] GMAIL_SEND_EMAIL - Sends email to self
- [ ] GMAIL_REPLY_TO_EMAIL - Replies to email

**Result**: _____ / 2 passed

**Manual Verification**:
- [ ] Test email received in inbox
- [ ] Email sent to correct address (self)
- [ ] Subject line correct
- [ ] Body content correct
- [ ] Reply works and threads correctly

**Status**:
- [ ] ✅ All pass - FULL send capability confirmed
- [ ] ⚠️ Partial - DOCUMENT which send actions work
- [ ] ⏭️ Skipped - Can still build tools, test carefully

---

## Post-Test Validation

### Test Report Generated

- [ ] JSON report file created (`gmail_test_report_*.json`)
- [ ] Report shows success rate for each action
- [ ] Errors documented for failed tests

### Test Data Cleanup

- [ ] Test labels deleted (or marked for manual cleanup)
- [ ] Test drafts deleted (or marked for manual cleanup)
- [ ] Test emails in inbox (expected, delete manually)

### Gmail Account State

- [ ] No unexpected labels created
- [ ] No unexpected drafts remaining
- [ ] Inbox state matches pre-test (except test emails)
- [ ] No emails sent to external addresses

---

## Critical Actions for Tool Building

### Core Actions (MUST WORK)

- [ ] **GMAIL_SEND_EMAIL** - Confirmed working ✅
- [ ] **GMAIL_FETCH_EMAILS** - Status: _________
- [ ] **GMAIL_SEARCH_MESSAGES** - Status: _________
- [ ] **GMAIL_GET_MESSAGE** - Status: _________
- [ ] **GMAIL_CREATE_DRAFT** - Status: _________

### High Priority (SHOULD WORK)

- [ ] **GMAIL_REPLY_TO_EMAIL** - Status: _________
- [ ] **GMAIL_GET_THREAD** - Status: _________
- [ ] **GMAIL_MARK_READ** - Status: _________
- [ ] **GMAIL_ADD_LABEL** - Status: _________

### Medium Priority (NICE TO HAVE)

- [ ] **GMAIL_CREATE_LABEL** - Status: _________
- [ ] **GMAIL_LIST_LABELS** - Status: _________
- [ ] **GMAIL_DELETE_DRAFT** - Status: _________

---

## Go/No-Go Decision

### Minimum Requirements to Build Tools

- [ ] ✅ Phase 1: 100% pass (all read actions work)
- [ ] ✅ Phase 2: 80%+ pass (organization actions mostly work)
- [ ] ✅ GMAIL_SEND_EMAIL confirmed working
- [ ] ✅ GMAIL_FETCH_EMAILS confirmed working
- [ ] ✅ GMAIL_CREATE_DRAFT confirmed working

### Recommended Requirements

- [ ] ✅ Phase 1: 100% pass
- [ ] ✅ Phase 2: 90%+ pass
- [ ] ✅ Phase 3: 100% pass
- [ ] ✅ Phase 4: 100% pass
- [ ] ✅ Manual validation complete
- [ ] ✅ No production impact

### Decision

**GO** ✅ - All minimum requirements met, proceed with tool building

**CONDITIONAL GO** ⚠️ - Some requirements met, build with limitations
- Document which actions work
- Note limitations in tool descriptions
- Plan for future enhancements

**NO GO** ❌ - Critical requirements not met
- Investigate and fix issues
- Re-test before proceeding

**Status**: _________________ (GO / CONDITIONAL GO / NO GO)

---

## Action Documentation (Fill in from tests)

### Confirmed Working Actions

List all actions that passed tests:

1. GMAIL_SEND_EMAIL ✅ (already confirmed)
2. _____________________________________
3. _____________________________________
4. _____________________________________
5. _____________________________________
6. _____________________________________
7. _____________________________________
8. _____________________________________
9. _____________________________________
10. _____________________________________

### Actions with Limitations

List actions that work but have issues:

1. _____________________________________
   - Issue: _____________________________
   - Workaround: ________________________

2. _____________________________________
   - Issue: _____________________________
   - Workaround: ________________________

### Non-Working Actions

List actions that failed tests:

1. _____________________________________
   - Error: _____________________________
   - Impact: ____________________________

2. _____________________________________
   - Error: _____________________________
   - Impact: ____________________________

---

## Tool Development Priority

Based on test results, build tools in this order:

### Week 1: Core Tools
- [ ] GmailSendTool (GMAIL_SEND_EMAIL) - Already validated
- [ ] GmailFetchTool (GMAIL_FETCH_EMAILS)
- [ ] GmailSearchTool (GMAIL_SEARCH_MESSAGES)

### Week 2: Draft & Reply Tools
- [ ] GmailCreateDraftTool (GMAIL_CREATE_DRAFT)
- [ ] GmailReplyTool (GMAIL_REPLY_TO_EMAIL)
- [ ] GmailGetMessageTool (GMAIL_GET_MESSAGE)

### Week 3: Organization Tools
- [ ] GmailMarkReadTool (GMAIL_MARK_READ)
- [ ] GmailAddLabelTool (GMAIL_ADD_LABEL)
- [ ] GmailGetThreadTool (GMAIL_GET_THREAD)

### Week 4: Advanced Tools
- [ ] Additional actions based on test results
- [ ] Integration testing
- [ ] Error handling improvements

---

## Notes & Observations

### Test Execution Date

**Date**: _____________________
**Tester**: Test Automation Specialist
**Test Duration**: _____________________

### Observations

**What worked well**:
-
-
-

**Issues encountered**:
-
-
-

**Surprises/Unexpected behavior**:
-
-
-

### Recommendations

**Immediate actions**:
1.
2.
3.

**Before building tools**:
1.
2.
3.

**Future considerations**:
1.
2.
3.

---

## Sign-Off

### Test Automation Specialist

**Tests Complete**: [ ] YES [ ] NO
**Report Generated**: [ ] YES [ ] NO
**Cleanup Done**: [ ] YES [ ] NO
**Ready to Build**: [ ] YES [ ] NO [ ] CONDITIONAL

**Signature**: _____________________
**Date**: _____________________

### Master Coordination Agent Review

**Results Reviewed**: [ ] YES [ ] NO
**Strategy Approved**: [ ] YES [ ] NO
**Proceed with Build**: [ ] YES [ ] NO [ ] CONDITIONAL

**Notes**:
_________________________________________
_________________________________________
_________________________________________

**Signature**: _____________________
**Date**: _____________________

---

**Last Updated**: 2025-11-01
**Document Version**: 1.0
**Next Review**: After test execution
