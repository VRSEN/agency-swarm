# Gmail Composio SDK Testing Suite

**Complete test automation infrastructure for validating Gmail actions before building Agency Swarm tools.**

---

## Quick Start (5 Minutes)

```bash
# Navigate to project
cd /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram

# Run safe tests (read-only, zero risk)
python test_all_gmail_actions.py
# When prompted, enter: 1

# Run organization tests (low risk, reversible)
python test_all_gmail_actions.py
# When prompted, enter: 2

# Check results
ls -lt gmail_test_report_*.json | head -1
```

**See**: `QUICK_TEST_GUIDE.md` for detailed instructions

---

## Documentation Overview

| File | Purpose | Use When |
|------|---------|----------|
| **QUICK_TEST_GUIDE.md** | 5-minute quick start | You want to run tests NOW |
| **GMAIL_TESTING_STRATEGY.md** | Complete strategy (22 pages) | You need full details |
| **VALIDATION_CHECKLIST.md** | Pre-build checklist | You're ready to build tools |
| **TEST_AUTOMATION_REPORT.md** | Technical report | You want comprehensive overview |
| **test_all_gmail_actions.py** | Test script (757 lines) | Run this to execute tests |

---

## What This Tests

### Phase 1: Read-Only Actions (SAFE - Zero Risk)
- Fetch emails from inbox
- Search for specific emails
- Get message details
- Get email threads
- List all labels

**Risk**: None - Only reads data

### Phase 2: Organization Actions (LOW RISK - Reversible)
- Create labels
- Add/remove labels
- Mark read/unread

**Risk**: Low - All changes can be undone

### Phase 3: Draft Actions (MEDIUM RISK - No Send)
- Create email drafts
- Retrieve draft details

**Risk**: Medium - Creates content but doesn't send

### Phase 4: Send Actions (HIGH RISK - Actual Emails)
- Send email (to self only)
- Reply to email

**Risk**: High - Sends real emails (with confirmation)

---

## Why Test Before Building?

### Problem
Building Agency Swarm tools for unverified actions leads to:
- ❌ Runtime failures in production
- ❌ Wasted development time
- ❌ Incomplete tool functionality
- ❌ Unknown API limitations

### Solution
Test-first approach ensures:
- ✅ Only build tools for working actions
- ✅ Understand parameter formats
- ✅ Know error patterns
- ✅ Document limitations upfront

---

## Test Results Format

### Console Output
```
================================================================================
PHASE 1: READ-ONLY ACTIONS (SAFE)
================================================================================

✅ GMAIL_FETCH_EMAILS [PASS]
   Retrieved: 5 emails

✅ GMAIL_SEARCH_MESSAGES [PASS]
   Found: 3 unread emails

✅ GMAIL_GET_MESSAGE [PASS]
   Message ID: abc123...

================================================================================
TEST RESULTS SUMMARY
================================================================================
TOTAL: 5 tests
✅ PASSED: 5
❌ FAILED: 0
Success Rate: 100.0%
================================================================================
```

### JSON Report
```json
{
  "summary": {
    "total": 5,
    "passed": 5,
    "failed": 0,
    "success_rate": 100.0
  },
  "results": {
    "phase_1_read_only": {
      "fetch_emails": {
        "success": true,
        "action": "GMAIL_FETCH_EMAILS",
        "result": {...}
      }
    }
  }
}
```

---

## Safety Features

### Built-In Protection
- ✅ **Test emails only sent to self** (info@mtlcraftcocktails.com)
- ✅ **Manual confirmation** required for risky actions
- ✅ **Clear test labels** (TEST_COMPOSIO_*)
- ✅ **Automatic cleanup** of test data
- ✅ **Phase-based execution** (run only what you need)
- ✅ **Rollback procedures** documented

### What Can't Break
- Your Gmail inbox (test emails go to self)
- Your contacts (no external emails)
- Your production labels (test labels clearly marked)
- Your production emails (no modifications)

---

## Minimum Testing Requirements

Before building ANY tools, must complete:

- [ ] **Phase 1 tests** (2 minutes) - 100% pass rate required
- [ ] **Phase 2 tests** (2 minutes) - 80%+ pass rate required
- [ ] **Validation checklist** - All critical actions confirmed
- [ ] **GMAIL_SEND_EMAIL** - Still working (confirmed on 2025-10-31)

**Total time**: 5 minutes
**Risk**: Zero (read-only and reversible actions)

---

## Recommended Testing Workflow

### Day 1: Safe Validation
```bash
# Test read-only actions (100% safe)
python test_all_gmail_actions.py  # Phase 1

# Test organization actions (reversible)
python test_all_gmail_actions.py  # Phase 2

# Review results
cat gmail_test_report_*.json | python -m json.tool
```

### Day 2: Draft Testing
```bash
# Test draft creation (no send)
python test_all_gmail_actions.py  # Phase 3

# Check Gmail drafts folder
# Verify test drafts appear
# Confirm no emails sent
```

### Day 3: Send Testing (Optional)
```bash
# Test send actions (with caution)
python test_all_gmail_actions.py  # Phase 4

# Confirm each send action
# Check inbox for test emails
# Verify no external sends
```

### Day 4: Tool Building
```bash
# Complete validation checklist
# Document working actions
# Start building tools
# Begin with GmailSendTool (already confirmed)
```

---

## After Testing

### If Tests Pass ✅

1. Open `VALIDATION_CHECKLIST.md`
2. Fill in results for each phase
3. Document working action names
4. Make go/no-go decision
5. Start building tools

### Priority Tool Building Order

**Week 1** (Critical):
1. GmailSendTool (GMAIL_SEND_EMAIL) - Already confirmed
2. GmailFetchTool (GMAIL_FETCH_EMAILS)
3. GmailSearchTool (GMAIL_SEARCH_MESSAGES)

**Week 2** (High Priority):
4. GmailCreateDraftTool (GMAIL_CREATE_DRAFT)
5. GmailReplyTool (GMAIL_REPLY_TO_EMAIL)
6. GmailGetMessageTool (GMAIL_GET_MESSAGE)

**Week 3** (Medium Priority):
7. GmailMarkReadTool (GMAIL_MARK_READ)
8. GmailAddLabelTool (GMAIL_ADD_LABEL)
9. GmailGetThreadTool (GMAIL_GET_THREAD)

---

## Troubleshooting

### Tests Won't Run

**Error**: "API Key not provided"
```bash
# Check credentials
cat .env | grep COMPOSIO_API_KEY

# Should show: COMPOSIO_API_KEY=ak_suouXXwN2bd7UvBbjJvu
```

**Error**: "Entity ID not found"
```bash
# Verify entity ID
cat .env | grep GMAIL_ENTITY_ID

# Should show: GMAIL_ENTITY_ID=pg-test-5fef8fe8-9810-4900-8ebf-9de6c1057220
```

**Error**: "Connection not found"
```bash
# Check connection
composio connections list

# Should show Gmail connection: 0d6c0e2d-7fd8-4700-89c0-17a871ae03da
```

### Tests Fail

**Check**:
1. Gmail connection still active
2. OAuth token not expired
3. Gmail API permissions correct
4. Account has emails/labels to test

**Solutions**:
- Re-run `composio login`
- Refresh OAuth: `python setup_connections.py`
- Send yourself test emails first
- Check detailed error in JSON report

---

## Project Structure

```
voice_email_telegram/
├── test_all_gmail_actions.py          # Main test suite (RUN THIS)
├── test_composio_sdk_gmail.py         # Existing send test (confirmed working)
├── QUICK_TEST_GUIDE.md                # Start here (5-minute guide)
├── GMAIL_TESTING_STRATEGY.md          # Full documentation (22 pages)
├── VALIDATION_CHECKLIST.md            # Pre-build checklist
├── TEST_AUTOMATION_REPORT.md          # Technical report
├── README_TESTING.md                  # This file
├── .env                               # Credentials (configured)
└── [Generated] gmail_test_report_*.json  # Test results
```

---

## Key Files

### Test Script
**File**: `test_all_gmail_actions.py` (757 lines)
**Purpose**: Execute all Gmail action tests
**Usage**: `python test_all_gmail_actions.py`

### Quick Start
**File**: `QUICK_TEST_GUIDE.md` (8 pages)
**Purpose**: Get testing in 5 minutes
**Usage**: Read first, then run tests

### Complete Strategy
**File**: `GMAIL_TESTING_STRATEGY.md` (22 pages)
**Purpose**: Comprehensive testing documentation
**Usage**: Reference for detailed procedures

### Checklist
**File**: `VALIDATION_CHECKLIST.md` (12 pages)
**Purpose**: Pre-build validation tracking
**Usage**: Fill out after tests complete

---

## Success Metrics

### Minimum Viable Testing (MVT)
- ✅ Phase 1: 100% pass (5/5 actions)
- ✅ Phase 2: 80%+ pass (4/5 actions)
- ✅ GMAIL_SEND_EMAIL: Working

**Result**: Can build core tools

### Ideal Testing (Production-Ready)
- ✅ Phase 1: 100% pass
- ✅ Phase 2: 90%+ pass
- ✅ Phase 3: 100% pass
- ✅ Phase 4: 100% pass

**Result**: Can build all tools with confidence

---

## Time Investment

| Activity | Time | Value |
|----------|------|-------|
| Initial testing (Phases 1-2) | 5 min | Critical |
| Draft testing (Phase 3) | 2 min | High |
| Send testing (Phase 4) | 2 min | Optional |
| Review results | 5 min | High |
| Complete checklist | 10 min | High |
| **Total** | **24 min** | **Prevents hours of debugging** |

**ROI**: 20-30 minutes of testing saves 10+ hours of debugging broken tools

---

## What's Already Confirmed

From `test_composio_sdk_gmail.py` (working as of 2025-10-31):

- ✅ **GMAIL_SEND_EMAIL** - Confirmed working
  - Sends email successfully
  - Parameters: recipient_email, subject, body, is_html
  - Tested with: info@mtlcraftcocktails.com
  - Status: Production ready

**Next**: Validate remaining 13+ actions before building more tools

---

## Support & Resources

### Documentation
- `QUICK_TEST_GUIDE.md` - Quick start
- `GMAIL_TESTING_STRATEGY.md` - Full details
- `VALIDATION_CHECKLIST.md` - Tracking
- `TEST_AUTOMATION_REPORT.md` - Technical overview

### External Resources
- Composio Docs: https://docs.composio.dev
- Gmail API Docs: https://developers.google.com/gmail/api
- Agency Swarm: https://github.com/VRSEN/agency-swarm

### Test Script Help
```bash
# Run with help
python test_all_gmail_actions.py --help

# Or just run and follow prompts
python test_all_gmail_actions.py
```

---

## Anti-Hallucination Protocol

### Test-First Methodology

This testing suite follows strict anti-hallucination principles:

1. **Test before claiming** - No action is "working" until tested
2. **Evidence-based** - All results documented in JSON
3. **Manual verification** - Check Gmail UI to confirm
4. **Honest reporting** - PASS/FAIL/SKIP (no guessing)
5. **Clear documentation** - Exact parameters and errors recorded

### What This Prevents

❌ **Before**: "These actions should work..." (hallucination)
✅ **After**: "These 12 actions passed tests, 2 failed with [specific errors]" (evidence)

---

## Next Steps

### Right Now (5 minutes)
```bash
# Run read-only tests
python test_all_gmail_actions.py  # Enter: 1
```

### Today (15 minutes)
1. Run Phase 1 and Phase 2 tests
2. Review test report
3. Complete validation checklist
4. Make go/no-go decision

### This Week
1. Build GmailSendTool (already validated)
2. Build GmailFetchTool
3. Build GmailSearchTool
4. Test tools individually
5. Integration test

### Next Week
1. Build remaining high-priority tools
2. Add to Voice Email Telegram Agency
3. End-to-end testing
4. Production deployment

---

## Questions?

- **Quick start**: See `QUICK_TEST_GUIDE.md`
- **Full details**: See `GMAIL_TESTING_STRATEGY.md`
- **Checklist**: See `VALIDATION_CHECKLIST.md`
- **Technical**: See `TEST_AUTOMATION_REPORT.md`

---

**Created**: 2025-11-01
**Author**: Test Automation Specialist Agent
**Project**: Voice Email Telegram Agency
**Location**: `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram`

**Status**: ✅ Ready to test
**Next Action**: Run Phase 1 tests
**Time Required**: 5 minutes

---

## TL;DR

```bash
# 1. Run safe tests
python test_all_gmail_actions.py  # Enter: 1,2

# 2. Check results
cat gmail_test_report_*.json | python -m json.tool | grep -A 10 "summary"

# 3. Build tools
# If tests pass: Start with GmailSendTool (already confirmed working)
```

**That's it. Test first, build second. Zero hallucination, 100% evidence-based.**
