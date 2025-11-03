# Quick Fix Reference Card

**2-Hour Fix for Critical Telegram Bot Issues**

---

## Issue 1: Context Overflow (30 min)

### Fix: Add ModelSettings with truncation

**File:** `email_specialist/email_specialist.py`

```python
# ADD THIS IMPORT
from agents import ModelSettings

# REPLACE THIS
email_specialist = Agent(
    name="EmailSpecialist",
    description="Drafts professional emails from voice input and manages Gmail operations",
    instructions=os.path.join(_current_dir, "instructions.md"),
    tools_folder=os.path.join(_current_dir, "tools"),
    model="gpt-4o",
    temperature=0.5,                    # ❌ DEPRECATED
    max_completion_tokens=25000,        # ❌ DEPRECATED
)

# WITH THIS
email_specialist = Agent(
    name="EmailSpecialist",
    description="Drafts professional emails from voice input and manages Gmail operations",
    instructions=os.path.join(_current_dir, "instructions.md"),
    tools_folder=os.path.join(_current_dir, "tools"),
    model="gpt-4o",
    model_settings=ModelSettings(       # ✅ NEW
        temperature=0.5,
        max_tokens=25000,
        truncation="auto"               # ✅ CRITICAL FIX
    )
)
```

**Apply same fix to:**
- `ceo/ceo.py`
- `memory_manager/memory_manager.py`
- `voice_handler/voice_handler.py`

---

## Issue 2: Intent Routing (1 hour)

### Fix: Add CRITICAL ROUTING RULES

**File:** `ceo/instructions.md`

**Location:** Insert after line 13 (after "## Core Responsibilities")

```markdown
---

## ⚡ CRITICAL ROUTING RULES ⚡

**CHECK THESE RULES FIRST before delegating to any agent.**

### 🔍 Rule 1: FETCH Operations (User Wants to READ Emails)

**Explicit Trigger Phrases:**
- "What is the last email" → GmailFetchEmails (max_results=1)
- "Show my latest email" → GmailFetchEmails (max_results=1)
- "What are my emails" → GmailFetchEmails (query="")
- "Check my inbox" → GmailFetchEmails (query="")
- "Show unread emails" → GmailFetchEmails (query="is:unread")
- "Read the email from [person]" → GmailFetchEmails (query="from:[email]")
- "Find emails about [topic]" → GmailFetchEmails (query="[topic]")

**Key Verbs:** what, show, list, read, check, find, search, get, view

**Action:** Immediately delegate to EmailSpecialist with GmailFetchEmails

---

### ✍️ Rule 2: DRAFT/SEND Operations (User Wants to CREATE Emails)

**Explicit Trigger Phrases:**
- "Draft an email to..." → Initiate draft workflow
- "Send email to..." → Initiate draft-then-send workflow
- "Create email for..." → Initiate draft workflow
- "Compose message to..." → Initiate draft workflow

**Key Verbs:** send, draft, create, compose, write

**Action:** Execute draft-approve-send workflow

---

### ❓ Rule 3: When Uncertain

If unclear:
1. Question words ("what", "which") → FETCH
2. Display verbs ("show", "check") → FETCH
3. Creation verbs ("send", "draft") → DRAFT
4. Still unclear? → ASK USER: "Would you like me to show existing emails or draft a new one?"

---

## Gmail Intent Routing (Detailed Reference)

[Keep existing content...]
```

---

## Testing

### Test Context Fix
```bash
python test_context_management.py
# Expected: 25/25 operations succeed, zero context errors
```

### Test Intent Routing
```bash
python test_intent_routing.py
# Expected: 13/13 tests pass, 100% success rate
```

### Manual Tests
```
1. "What is the last email that came in?" → Should FETCH
2. "Show my unread emails" → Should FETCH
3. "Draft an email to john@example.com" → Should DRAFT
```

---

## Deployment

### Backup
```bash
cd /Users/ashleytower/Desktop/agency-swarm-voice/voice_email_telegram
cp email_specialist/email_specialist.py email_specialist/email_specialist.py.backup
cp ceo/ceo.py ceo/ceo.py.backup
cp ceo/instructions.md ceo/instructions.md.backup
```

### Deploy
1. Apply Fix 1 to all agent .py files (30 min)
2. Apply Fix 2 to ceo/instructions.md (30 min)
3. Run test suite (30 min)
4. Deploy to production

### Rollback (if needed)
```bash
cp email_specialist/email_specialist.py.backup email_specialist/email_specialist.py
cp ceo/ceo.py.backup ceo/ceo.py
cp ceo/instructions.md.backup ceo/instructions.md
```

---

## Success Criteria

✅ Zero `context_length_exceeded` errors
✅ "What is the last email" routes to FETCH
✅ All test cases pass
✅ No deprecation warnings

---

**Total Time:** 2 hours
**Risk:** Low
**Impact:** Fixes both production blockers

**Full Documentation:**
- CRITICAL_FIXES_ANALYSIS.md (detailed analysis)
- IMPLEMENTATION_GUIDE.md (step-by-step)
- BACKEND_ARCHITECT_REPORT.md (executive summary)
