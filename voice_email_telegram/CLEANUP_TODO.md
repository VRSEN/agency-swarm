# Cleanup & Testing TODO

## 🗑️ Files to Delete (Over-Engineering)

### Verification Scripts (One-off tests)
```bash
rm verify_gmail_search_people_integration.py
rm verify_email_sent.py
rm gmail_actions_test_results.json
rm telegram_bot.log
```

### Empty/Mistake Directories
```bash
rm -rf "Moved test files. Remaining in tools directory:"
rm -rf mv
rm -rf voice_email_telegram  # Duplicate directory (if empty)
```

### Old Logs
```bash
rm -rf logs  # If not actively used
```

## ✅ Testing Priority (For Tusk)

### Phase 1: Core Business Logic (Do Next PR)
Create these test files for Tusk to populate:

1. **test_rube_mcp_client.py** - HIGH PRIORITY
   - Test gmail_send_email action
   - Test gmail_fetch_emails action
   - Test error handling (401, 500, network errors)
   - Mock all Composio API calls

2. **test_classify_intent.py** - HIGH PRIORITY
   - Test email drafting intent detection
   - Test email reading intent detection
   - Test voice message intent detection
   - Edge cases: ambiguous intents

3. **test_telegram_bot_listener.py** - HIGH PRIORITY
   - Test message handling
   - Test voice message handling
   - Mock Telegram API calls
   - Mock agency.get_completion()

### Phase 2: Agent Tools (Later)
4. **test_mem0_operations.py**
   - Test Mem0Add, Mem0Search, Mem0GetAll, Mem0Update
   - Mock Mem0 API

5. **test_workflow_coordinator.py**
   - Test workflow state transitions
   - Test handoff logic

6. **test_draft_email.py**
   - Test email drafting from voice input
   - Test context integration with Mem0

### Phase 3: Helper Functions (Optional)
7. **test_email_validation.py**
8. **test_contact_learning.py**

## 🚫 What NOT to Test

- `__init__.py` files (just imports)
- Agent configuration files (ceo.py, email_specialist.py, etc.) - already tested in test_agents_configuration.py
- `agency_manifesto.md` (documentation)
- `requirements.txt` (not code)

## 📋 Recommended Next Steps

1. **Merge current PR** (utils.py testing is done)
2. **Create cleanup PR** - Delete unnecessary files
3. **Create test stubs PR** - Add empty test files for Phase 1
4. **Let Tusk populate tests** - It will generate tests automatically
5. **Iterate on failures** - Fix issues Tusk finds

## 🎯 Testing Coverage Goals

Based on TESTING_GUIDELINES.md:

- **Critical paths**: 90%+ (RubeMCPClient, ClassifyIntent, telegram_bot_listener)
- **Integration code**: 70%+ (Agent communication, tool execution)
- **Configuration**: 50%+ (Already done!)

## 💡 Tusk Integration Strategy

**For each new feature:**
1. Write minimal code
2. Open PR
3. Tusk generates tests
4. Fix failures
5. Tusk commits passing tests
6. Merge

**Tusk doesn't:**
- Delete unused code (manual cleanup)
- Refactor over-engineering (manual review)
- Detect architectural issues (code review)

## 🔍 Over-Engineering Check

Current concerns:
- ✅ RubeMCPClient is good (replaced 25 tools with 1)
- ❓ Do we need ALL 10 Mem0 tools or can some be combined?
- ❓ Are ImportContactsFromCSV and ImportContactsFromGoogleSheets both used?
- ✅ Tool count per agent is good (CEO: 3, Email: 6, Memory: 10, Voice: 6)

**Recommendation:** Keep current structure. It's clean post-cleanup.
