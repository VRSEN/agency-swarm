# Critical Fixes - Step-by-Step Implementation Guide

**Quick Start:** Execute both fixes in under 2 hours with this guide.

---

## Fix 1: Context Window Overflow (30 minutes)

### Step 1: Update EmailSpecialist Agent Configuration

**File:** `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/email_specialist/email_specialist.py`

**Current Code (Lines 1-16):**
```python
import os

from agency_swarm import Agent

_current_dir = os.path.dirname(os.path.abspath(__file__))

email_specialist = Agent(
    name="EmailSpecialist",
    description="Drafts professional emails from voice input and manages Gmail operations",
    instructions=os.path.join(_current_dir, "instructions.md"),
    tools_folder=os.path.join(_current_dir, "tools"),
    model="gpt-4o",
    temperature=0.5,                    # DEPRECATED
    max_completion_tokens=25000,        # DEPRECATED
)
```

**New Code:**
```python
import os

from agency_swarm import Agent
from agents import ModelSettings  # NEW IMPORT

_current_dir = os.path.dirname(os.path.abspath(__file__))

email_specialist = Agent(
    name="EmailSpecialist",
    description="Drafts professional emails from voice input and manages Gmail operations",
    instructions=os.path.join(_current_dir, "instructions.md"),
    tools_folder=os.path.join(_current_dir, "tools"),
    model="gpt-4o",
    model_settings=ModelSettings(      # NEW
        temperature=0.5,
        max_tokens=25000,
        truncation="auto"              # CRITICAL: Enables automatic context management
    )
)
```

**Changes:**
1. Add import: `from agents import ModelSettings`
2. Replace deprecated parameters with `model_settings=ModelSettings(...)`
3. Add `truncation="auto"` to enable automatic context pruning

**Impact:**
- ✅ Eliminates context_length_exceeded errors
- ✅ Removes deprecation warnings
- ✅ No breaking changes to existing functionality

---

### Step 2: Apply Same Fix to CEO Agent

**File:** `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/ceo/ceo.py`

**Current Code:**
```python
import os

from agency_swarm import Agent

_current_dir = os.path.dirname(os.path.abspath(__file__))

ceo = Agent(
    name="CEO",
    description="Orchestrates the voice-to-email workflow and manages the approval state machine",
    instructions=os.path.join(_current_dir, "instructions.md"),
    tools_folder=os.path.join(_current_dir, "tools"),
    model="gpt-4o",
    temperature=0.5,
    max_completion_tokens=25000,
)
```

**New Code:**
```python
import os

from agency_swarm import Agent
from agents import ModelSettings  # NEW IMPORT

_current_dir = os.path.dirname(os.path.abspath(__file__))

ceo = Agent(
    name="CEO",
    description="Orchestrates the voice-to-email workflow and manages the approval state machine",
    instructions=os.path.join(_current_dir, "instructions.md"),
    tools_folder=os.path.join(_current_dir, "tools"),
    model="gpt-4o",
    model_settings=ModelSettings(
        temperature=0.5,
        max_tokens=25000,
        truncation="auto"
    )
)
```

---

### Step 3: Apply to Remaining Agents (Optional but Recommended)

**Files to update:**
- `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/memory_manager/memory_manager.py`
- `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/voice_handler/voice_handler.py`

**Same pattern:** Replace deprecated parameters with ModelSettings.

---

## Fix 2: CEO Intent Routing (1 hour)

### Step 1: Add Critical Routing Rules Section

**File:** `/Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram/ceo/instructions.md`

**Insert after line 13** (after "## Core Responsibilities")

```markdown
---

## ⚡ CRITICAL ROUTING RULES ⚡

**CHECK THESE RULES FIRST before delegating to any agent.**

### 🔍 Rule 1: FETCH Operations (User Wants to READ Emails)

User wants to VIEW/SEE/CHECK existing emails - NOT create new ones.

**Explicit Trigger Phrases:**
- "What is the last email" → GmailFetchEmails (max_results=1, query="")
- "Show my latest email" → GmailFetchEmails (max_results=1)
- "What are my emails" → GmailFetchEmails (query="")
- "Show unread emails" → GmailFetchEmails (query="is:unread")
- "Read the email from [person]" → GmailFetchEmails (query="from:[email]")
- "Check my inbox" → GmailFetchEmails (query="")
- "Find emails about [topic]" → GmailFetchEmails (query="[topic]")
- "Search for [keyword]" → GmailFetchEmails (query="[keyword]")

**Key Verbs for FETCH:** what, show, list, read, check, find, search, get, view, display

**Action:** Immediately delegate to EmailSpecialist with GmailFetchEmails tool.

**Example:**
```
User: "What is the last email that came in?"
CEO Action: Delegate to EmailSpecialist → GmailFetchEmails(max_results=1, query="")
```

---

### ✍️ Rule 2: DRAFT/SEND Operations (User Wants to CREATE Emails)

User wants to COMPOSE/WRITE/SEND new emails.

**Explicit Trigger Phrases:**
- "Draft an email to [person]" → Initiate draft workflow
- "Send email to [person]" → Initiate draft-then-send workflow
- "Create email for [person]" → Initiate draft workflow
- "Compose message to [person]" → Initiate draft workflow
- "Write to [person]" → Initiate draft workflow

**Key Verbs for DRAFT:** send, draft, create, compose, write, email [someone]

**Action:** Execute your primary draft-approve-send workflow.

**Example:**
```
User: "Send an email to john@example.com about the meeting"
CEO Action: Initiate draft-approve-send workflow
```

---

### ❓ Rule 3: When Uncertain (Disambiguation)

If query is ambiguous, use these heuristics:

**Heuristic Priority:**
1. **Question words** ("what", "which") → FETCH
2. **Display verbs** ("show", "check", "read") → FETCH
3. **Creation verbs** ("send", "draft", "create") → DRAFT
4. **Preposition "to [person]"** → DRAFT
5. **Still unclear?** → ASK USER

**Clarification Template:**
```
"I can either:
A) Show you existing emails (fetch from your inbox)
B) Draft a new email to send

Which would you like?"
```

---

### ⚠️ Common Misrouting Prevention

**These are FETCH, not DRAFT:**
- ❌ "What is the last email that came in?" → FETCH (not draft!)
- ❌ "Show my latest email" → FETCH (not draft!)
- ❌ "Check if I have any new emails" → FETCH (not draft!)
- ❌ "Read the email from John" → FETCH (not draft!)

**These are DRAFT, not FETCH:**
- ✅ "Draft an email to Sarah" → DRAFT (not fetch!)
- ✅ "Send email to team@company.com" → DRAFT (not fetch!)
- ✅ "Create an email for the client" → DRAFT (not fetch!)

---
```

### Step 2: Reorganize Gmail Intent Routing Section

**Update line 14 heading:**
```markdown
## Gmail Intent Routing (Detailed Reference)

**Note:** Always apply CRITICAL ROUTING RULES first. This section provides detailed
Gmail search operators and advanced intent patterns.
```

**No other changes needed** - existing content remains intact but is now secondary to
the priority routing rules.

---

### Step 3: Update Workflow Steps Section (Line 188+)

**Add before line 189:**
```markdown
## Workflow Steps

**IMPORTANT:** Before executing ANY workflow, always check CRITICAL ROUTING RULES above
to ensure you're not misrouting a fetch request as a draft workflow.

---
```

**Keep all existing workflow steps** (lines 189-233) unchanged.

---

## Validation & Testing

### Test 1: Context Overflow Fix

**Run this test to verify context management:**

```python
# test_context_management.py
from agency import agency

# Simulate 25 consecutive email operations
print("Testing context window management...")
print("=" * 60)

for i in range(25):
    query = f"Show me unread email number {i}"
    print(f"\nOperation {i+1}/25: {query}")

    try:
        response = agency.get_completion(query)
        if "error" in response.lower() and "context" in response.lower():
            print(f"  ❌ FAILED: Context overflow at operation {i+1}")
            break
        else:
            print(f"  ✅ SUCCESS")
    except Exception as e:
        if "context_length_exceeded" in str(e):
            print(f"  ❌ FAILED: Context overflow at operation {i+1}")
            break
        raise

print("\n" + "=" * 60)
print("✅ Test completed - No context overflow!")
```

**Expected Result:** All 25 operations succeed without context errors.

---

### Test 2: Intent Routing Fix

**Run this test to verify CEO routing:**

```python
# test_intent_routing.py
from agency import agency

test_cases = [
    # Format: (query, expected_action, reasoning)
    ("What is the last email that came in?", "FETCH", "Should route to GmailFetchEmails"),
    ("Show my latest email", "FETCH", "Display verb indicates fetch"),
    ("Check my inbox", "FETCH", "Read operation, not write"),
    ("What are my unread emails?", "FETCH", "Question about existing emails"),
    ("Find emails from john@example.com", "FETCH", "Search operation"),

    ("Draft an email to sarah@company.com", "DRAFT", "Explicit draft request"),
    ("Send email to team@startup.com", "DRAFT", "Explicit send request"),
    ("Create an email for the client", "DRAFT", "Creation verb indicates draft"),
    ("Compose a message to my boss", "DRAFT", "Composition request"),
]

print("Testing CEO Intent Routing...")
print("=" * 80)

passed = 0
failed = 0

for query, expected, reasoning in test_cases:
    print(f"\nQuery: '{query}'")
    print(f"Expected: {expected} - {reasoning}")

    response = agency.get_completion(query)

    # Analyze response to determine actual routing
    if expected == "FETCH":
        if "GmailFetchEmails" in response or "fetching" in response.lower():
            print("✅ PASS - Correctly routed to FETCH")
            passed += 1
        else:
            print("❌ FAIL - Incorrectly routed to DRAFT")
            print(f"Response: {response[:200]}...")
            failed += 1
    elif expected == "DRAFT":
        if "draft" in response.lower() or "workflow" in response.lower():
            print("✅ PASS - Correctly routed to DRAFT")
            passed += 1
        else:
            print("❌ FAIL - Incorrectly routed to FETCH")
            print(f"Response: {response[:200]}...")
            failed += 1

print("\n" + "=" * 80)
print(f"Results: {passed} passed, {failed} failed")
print(f"Success Rate: {(passed/(passed+failed)*100):.1f}%")
print("=" * 80)
```

**Expected Result:** 100% pass rate (9/9 test cases).

---

## Deployment Checklist

### Pre-Deployment
- [ ] Backup current files:
  ```bash
  cp email_specialist/email_specialist.py email_specialist/email_specialist.py.backup
  cp ceo/ceo.py ceo/ceo.py.backup
  cp ceo/instructions.md ceo/instructions.md.backup
  cp memory_manager/memory_manager.py memory_manager/memory_manager.py.backup
  cp voice_handler/voice_handler.py voice_handler/voice_handler.py.backup
  ```

### Implementation
- [ ] Apply Fix 1 to email_specialist.py
- [ ] Apply Fix 1 to ceo.py
- [ ] Apply Fix 1 to memory_manager.py (optional)
- [ ] Apply Fix 1 to voice_handler.py (optional)
- [ ] Apply Fix 2 to ceo/instructions.md

### Testing
- [ ] Run test_context_management.py
- [ ] Run test_intent_routing.py
- [ ] Test with real Telegram bot queries
- [ ] Verify no deprecation warnings in logs

### Validation
- [ ] Zero context_length_exceeded errors
- [ ] 100% correct fetch vs draft routing
- [ ] No breaking changes to existing workflows
- [ ] All Gmail tools still functional

### Post-Deployment
- [ ] Monitor logs for 24 hours
- [ ] Test with real users
- [ ] Document any edge cases discovered
- [ ] Update this guide if needed

---

## Rollback Plan

If issues arise, restore from backups:

```bash
# Rollback command
cp email_specialist/email_specialist.py.backup email_specialist/email_specialist.py
cp ceo/ceo.py.backup ceo/ceo.py
cp ceo/instructions.md.backup ceo/instructions.md
cp memory_manager/memory_manager.py.backup memory_manager/memory_manager.py
cp voice_handler/voice_handler.py.backup voice_handler/voice_handler.py

# Restart bot
# (Your bot restart command here)
```

---

## Success Criteria

### Fix 1: Context Window
- ✅ No context_length_exceeded errors over 100 operations
- ✅ All deprecation warnings removed
- ✅ Conversation flow preserved

### Fix 2: Intent Routing
- ✅ "What is the last email" correctly routes to FETCH
- ✅ 100% test suite pass rate
- ✅ No false draft triggers on read-only queries

---

## Troubleshooting

### Issue: Still getting context errors
**Solution:**
- Check that `from agents import ModelSettings` is imported
- Verify `truncation="auto"` is in ModelSettings
- Check Agency Swarm version: `pip show agency-swarm`

### Issue: Routing still ambiguous
**Solution:**
- Verify CRITICAL ROUTING RULES section is at top of instructions
- Check that section uses ⚡ emoji (ensures visibility)
- Test with exact phrases from test suite
- Add ValidateUserIntent tool (see CRITICAL_FIXES_ANALYSIS.md Appendix)

### Issue: Deprecation warnings persist
**Solution:**
- Ensure ALL parameters moved into ModelSettings
- No `temperature`, `max_completion_tokens` outside ModelSettings
- Restart Python process to clear cached module

---

## Time Estimates

- **Fix 1 Implementation:** 30 minutes
  - email_specialist.py: 5 min
  - ceo.py: 5 min
  - memory_manager.py: 5 min
  - voice_handler.py: 5 min
  - Testing: 10 min

- **Fix 2 Implementation:** 1 hour
  - Add CRITICAL ROUTING RULES: 30 min
  - Update section references: 10 min
  - Testing: 20 min

- **Total:** ~90 minutes (1.5 hours)

---

## Support

If you encounter issues:
1. Check CRITICAL_FIXES_ANALYSIS.md for detailed technical background
2. Review error logs in telegram_bot.log
3. Test with isolated test cases before full deployment
4. Consult Agency Swarm documentation: https://docs.agency-swarm.com

---

**Implementation Guide Version:** 1.0
**Last Updated:** 2025-11-02
**Author:** Backend Architect Agent
