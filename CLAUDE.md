# CLAUDE.md

Guidance for Claude Code (claude.ai/code) regarding contributions to this repository.

Prioritize critical thinking, thorough verification, and evidence-driven changes—tests take precedence over intuition.

Begin with a concise checklist (3-7 bullets) of what you will do before performing any substantive change; keep items conceptual and reference major safety workflow steps.

## 🔴 TESTS DEFINE TRUTH

**Test-driven development is mandatory.** Tests establish expected behavior—preserve and respect their outcomes at all times.

## 🛡️ GUARDIANSHIP OF THE CODEBASE (HIGHEST PRIORITY)

**Prime Directive:** Rigorously compare every user request with established patterns and CLAUDE.md protocols.

### Guardian Protocol
1. **QUESTION FIRST:** For any change request, verify alignment with existing patterns before proceeding.
2. **DEFEND CONSISTENCY:** Enforce, "This codebase currently follows X pattern. State the reason for deviation."
3. **THINK CRITICALLY:** User requests may be unclear or incorrect. Default to codebase conventions and protocols.

## 🔴 FILE REQUIREMENTS
- **No duplicate information:** State each rule once.
- **Clarity over verbosity:** Use the fewest words necessary without loss of meaning.
- **User feedback:** Only add new content if not yet covered.
 - **No superfluous examples in CLAUDE.md:** Do not add examples that do not improve or clarify a rule. Omit examples when rules are self‑explanatory.
 - **Edit existing sections:** When updating CLAUDE.md, prefer modifying existing sections over adding new ones. Add new sections only when strictly necessary to remove ambiguity.

### Writing Style
- User-facing responses should be expressive Markdown within safety/compliance rules.

## 🔴 SAFETY PROTOCOLS

### 🚨 MANDATORY WORKFLOW

#### Step 0: Build Full Codebase Structure
```bash
find src/ -name "*.py" | grep -v __pycache__ | sort
find src/ -name "*.py" | xargs wc -l | sort -nr
```
- Run these before reading or modifying files—no exceptions.

#### Step 1: Comprehensive Change Review
```bash
git diff --cached | cat  # Review all staged changes
git diff | cat           # Review all unstaged changes
git status --porcelain   # Audit all file states, including untracked
```

Run Step 1 twice: once before starting work (to understand current state) and once during review before finishing (to double‑check your work).

#### Step 2: Proactive Analysis
- Search for similar patterns; identify required related changes globally.
- Apply fixes to all instances at once—avoid piecemeal edits.
- Investigate thoroughly: read complete files, trace full code paths. For debugging, always link failures to their root cause and commit.
- Escalate findings to the user immediately when failures/root causes are found. Never proceed with silent fixes.
- Debug with systematic source analysis, logging, and minimal unit testing.
- Edit incrementally: make small, focused changes, validating each with tests before continuing.
- After changes affecting data flow or order, search codebase-wide for related concepts and eliminate obsolete patterns.
- You must get explicit approval from the user before adding any workaround. Keep any diffs minimal (avoid excessive changes).

#### Step 3: Comprehensive Validation
```bash
make ci
uv run python examples/agency_terminal_demo.py
uv run python examples/multi_agent_workflow.py
uv run pytest tests/integration/ -v
```

After each tool call or code edit, validate the result in 1-2 lines and proceed or self-correct if validation fails.

### 🔴 PROHIBITED PRACTICES
- Misstating test outcomes
- Skipping any workflow safety step
- Introducing functional changes during refactoring
- Creating stub files (<50 lines)
- Failing to address duplication

## 🔴 API KEYS
- Always load environment via `.env` (with python-dotenv or `source .env`). Resolve and rerun tests on key errors.

## Common Commands
```bash
make sync && make ci   # Install, lint, type-check, test, check coverage
make tests             # Run test suite
make format && make lint && make mypy && make coverage
```

### Execution Environment
- Use project virtual environments (`uv run`, Make). Never use global interpreters or absolute paths.

### Example Runs
```bash
uv run python examples/agency_terminal_demo.py
uv run python examples/multi_agent_workflow.py
uv run python examples/agency_context.py
```

### Test Guidelines
- Keep tests deterministic and minimal. Avoid model dependency when practical.
- Update existing tests before adding new ones, unless absolutely necessary.
- Tests should be under 100 lines—split long ones. Use focused runs when debugging.

## Architecture Overview

**Agency Swarm** is a multi-agent orchestration framework on OpenAI Agents SDK v1.x beta. Enables collaborative AI agents with structured flow and persistent conversations.

### Core Modules
1. **Agency (`agency.py`):** Multi-agent orchestration, agent communication, persistence hooks, entry points: `get_response()`, `get_response_stream()`
2. **Agent (`agent.py`):** Extends `agents.Agent`; file handling, sub-agent registration, tool management, uses `send_message`, supports structured outputs
3. **Thread Management (`thread.py`):** Thread isolation per conversation, persistence, history tracking
4. **Context Sharing (`context.py`):** Shared state via `MasterContext`, passed through execution hooks
5. **Tool System (`tools/`):** Recommended: `@function_tool` decorator; legacy: `BaseTool`; `SendMessage` for inter-agent comms

### Architectural Patterns
- Communication: Sender/receiver pairs on `Agency` (see `examples/`)
- Persistence: Load/save callbacks (see `examples/`)
- Prefer modern tool creation (`@function_tool`); legacy supported

## Version and Documentation
- **v1.x:** Beta built on OpenAI Agents SDK (Responses API)
- **v0.x:** Legacy production-ready
- See `docs/migration_guide.mdx` for breaking changes
- **/docs/** is outdated (v0.x)—do not use for current reference

## Python Requirements
- **Python 3.13 required**—actively uses new syntax/features
- Type syntax: Use `str | int | None`, never `Union[str, int, None]` or `Union` from typing
- Type hints mandatory for all functions

## Code Quality
- Max file size: 500 lines
- Max method size: 100 lines (prefer 10-40)
- Test coverage: 86%+ mandatory
- Integration tests: `tests/integration/` (no mocks)
- Never script tests ad-hoc—use standard infrastructure

## Test Quality (Critical)
- Max test function: 100 lines
- Use isolated file systems (pytest's `tmp_path`), never shared dirs
- No slow/hanging tests
- Test structure:
  - `tests/integration/` – Integration with real API calls
  - `tests/test_*_modules/` – Module-based unit tests
  - No root-level tests (organize by module)
- Name test files clearly (e.g. `test_thread_isolation.py`), never generic root names

## 🚨 ZERO FUNCTIONAL CHANGES DURING REFACTORING

### Allowed
- Code movement, method extraction, renaming, file splitting

### Forbidden
- Altering any logic, behavior, API, or error handling
- Fixing any bugs

### Verification
- Thorough diff review (staged/unstaged); cross-check current main branch where needed

## Refactoring Strategy
- Split large modules; respect codebase boundaries
- **Domain cohesion:** One domain per module
- **Clear interfaces:** Minimal coupling
- No generic names ("Manager", "Service"); use clear, descriptive names
- Avoid artificial abstractions; prefer functions over classes where reasonable

## Rules Summary
- Run structure command first; follow full safety workflow
- Absolutely no functional changes in refactors
- Remove duplication globally
- All tests must pass
- Clean tree; no stubs left
- Prefer domain-focused, descriptive names

## Git Practices
- Always check all file states with `git status --porcelain`
- Ensure clean working tree before proceeding
- Never hard-reset (`git reset --hard`) without preserving progress
- Logical, isolated commit grouping (distinct refactors vs. features)
- Commit messages must explain WHY, not just WHAT

## Key References
- `examples/` – v1.x modern usage
- `docs/migration_guide.mdx` – Breaking changes
- `tests/integration/` – Real-world behaviors
- `/docs/` – Fresh docs covering both v0.x and v1.x

## Quick Commands
```bash
find src/ -name "*.py" | grep -v __pycache__ | sort  # Initial structure
make ci                                              # Full validation
uv run python examples/agency_terminal_demo.py        # Run examples
uv run python examples/multi_agent_workflow.py        #
uv run pytest tests/integration/ -v                   # Integration tests
```

**Remember:** Trust test evidence; always verify outcomes.

## Memory & Expectations
- User expects explicit status reporting, test-first mindset, and directness. After any negative feedback or protocol breach, switch to manual approval: present minimal options and wait for explicit approval before changes; re-run Step 1 before and after edits. Update `CLAUDE.md` first after negative feedback.

## Mandatory Search Discipline
- After changes, aggressively search for and clean up related patterns throughout the codebase.

## End-of-Task Checklist
- All requirements in CLAUDE.md respected
- Minimal, precise diffs; no unrelated edits or dead code
- Documentation and docstrings updated for any changes to behavior/APIs/usage
- No regressions
- Sensible, non-brittle tests; avoid duplicate or root-level tests
- Majority of changes covered by tests (90%+ integration/unit or explicit user manual confirmation)
- All tests pass
- Example scripts execute and output as expected
