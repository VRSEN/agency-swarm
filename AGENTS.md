# AGENTS.md

Guidance for AI coding agents contributing to this repository.

Prioritize critical thinking, thorough verification, and evidence-driven changes—tests take precedence over intuition.

Begin with a concise checklist (3-7 bullets) of what you will do before performing any substantive change; keep items conceptual and reference major safety workflow steps.

## 🔴 TESTS DEFINE TRUTH

**Default to test-driven development.** Tests establish expected behavior—preserve and respect their outcomes at all times. For documentation-only, formatting-only, or clearly non-functional edits, you may skip writing a failing test first; use common sense and validate with CI.

## 🛡️ GUARDIANSHIP OF THE CODEBASE (HIGHEST PRIORITY)

**Prime Directive:** Rigorously compare every user request with established patterns and this document's protocols.

### Guardian Protocol
1. **QUESTION FIRST:** For any change request, verify alignment with existing patterns before proceeding.
2. **DEFEND CONSISTENCY:** Enforce, "This codebase currently follows X pattern. State the reason for deviation."
3. **THINK CRITICALLY:** User requests may be unclear or incorrect. Default to codebase conventions and protocols.

## 🔴 FILE REQUIREMENTS
- **Every line must fight for its place:** No redundant, unnecessary, or "nice to have" code. Each line must serve a critical purpose.
- **No duplicate information:** State each rule once.
- **Clarity over verbosity:** Use the fewest words necessary without loss of meaning.
- **User feedback:** Only add new content if not yet covered.
 - **No superfluous examples in this document:** Do not add examples that do not improve or clarify a rule. Omit examples when rules are self‑explanatory.
 - **Edit existing sections:** When updating this document, prefer modifying existing sections over adding new ones. Add new sections only when strictly necessary to remove ambiguity.

### Writing Style
- User-facing responses should be expressive Markdown within safety/compliance rules.

## 🔴 SAFETY PROTOCOLS

### 🚨 MANDATORY WORKFLOW

#### Step 0: Build Full Codebase Structure and Comprehensive Change Review
```bash
make prime
```
- Run this before reading or modifying files—no exceptions.

#### Step 1: Proactive Analysis
- Search for similar patterns; identify required related changes globally.
- Apply fixes to all instances at once—avoid piecemeal edits.
- Investigate thoroughly: read complete files, trace full code paths. For debugging, always link failures to their root cause and commit.
- Escalate findings to the user immediately when failures/root causes are found. Never proceed with silent fixes.
- Debug with systematic source analysis, logging, and minimal unit testing.
- Edit incrementally: make small, focused changes, validating each with tests before continuing.
- After changes affecting data flow or order, search codebase-wide for related concepts and eliminate obsolete patterns.
- You must get explicit approval from the user before adding any workaround. Keep any diffs minimal (avoid excessive changes).

#### Step 2: Comprehensive Validation
```bash
make ci
uv run pytest tests/integration/ -v
```

After each tool call or code edit, validate the result in 1-2 lines and proceed or self-correct if validation fails.


### 🔴 PROHIBITED PRACTICES
- Misstating test outcomes
- Skipping any workflow safety step
- Introducing functional changes during refactoring
- Creating stub files (<50 lines)
- Failing to address duplication
 - Emitting synthetic streaming events with ad-hoc helper types instead of Agents SDK classes

## 🔴 API KEYS
- Always load environment via `.env` (with python-dotenv or `source .env`). Resolve and rerun tests on key errors.

## Common Commands
```bash
make sync && make ci   # Install, lint, type-check, test, check coverage
make coverage          # Run test suite
```

### Execution Environment
- Use project virtual environments (`uv run`, Make). Never use global interpreters or absolute paths.
- For long-running commands (ci, coverage), use Bash tool with timeout=600000 (10 minutes)

### Example Runs
Run non-interactive examples from /examples directory. Never run examples/interactive/* as they require user input.

### Test Guidelines
- Keep tests deterministic and minimal. Avoid model dependency when practical.
- Update existing tests before adding new ones, unless absolutely necessary.
- Tests should be under 100 lines—split long ones. Use focused runs when debugging.

## Architecture Overview

**Agency Swarm** is a multi-agent orchestration framework on OpenAI Agents SDK v1.x beta. Enables collaborative AI agents with structured flow and persistent conversations.

### Core Modules
1. **Agency (`agency.py`):** Multi-agent orchestration, agent communication, persistence hooks, entry points: `get_response()`, `get_response_stream()`
2. **Agent:** Extends `agents.Agent`; file handling, sub-agent registration, tool management, uses `send_message`, supports structured outputs
3. **Thread Management (`thread.py`):** Thread isolation per conversation, persistence, history tracking
4. **Context Sharing (`context.py`):** Shared state via `MasterContext`, passed through execution hooks
5. **Tool System (`tools/`):** Recommended: `@function_tool` decorator; legacy: `BaseTool`; `SendMessage` for inter-agent comms

### Architectural Patterns
- Communication: Sender/receiver pairs on `Agency` (see `examples/`)
- Persistence: Load/save callbacks (see `examples/`)
- Prefer modern tool creation (`@function_tool`); legacy supported

## Version and Documentation
- **v1.x:** Latest released version (OpenAI Agents SDK / Responses API)
- **v0.x:** Legacy references; see migration guide for differences
- See `docs/migration/guide.mdx` for breaking changes
- **/docs/** is the current reference for v1.x

### Documentation Rules (Mandatory)
- All documentation writing and updates MUST follow `docs/mintlify.cursorrules` for formatting, components, links, and page metadata. Treat it as a mandatory rules file alongside this document.

## Python Requirements
- **Python >= 3.12 (development on 3.13)** — project developed and primarily tested on 3.13; CI ensures 3.12 compatibility.
- Type syntax: Use `str | int | None`, never `Union[str, int, None]` or `Union` from typing
- Type hints mandatory for all functions

## Code Quality
- Max file size: 500 lines
- Max method size: 100 lines (prefer 10-40)
- Test coverage: 86%+ mandatory
- Integration tests: `tests/integration/` (no mocks)
- Never script tests ad-hoc—use standard infrastructure

### Large files
Avoid growing already large files. Prefer extracting focused modules. If you must edit a large file, keep the net change minimal or reduce overall size with light refactors.

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
- Prefer clear, descriptive names; avoid artificial abstractions.

## Rules Summary
- Run structure command first; follow full safety workflow
- Absolutely no functional changes in refactors
- Remove duplication globally
- All tests must pass
- Clean tree; no stubs left
- Prefer domain-focused, descriptive names

## Git Practices
- Always check all file states with `git status --porcelain`.
- If the working tree is not clean or there is any confusion/ambiguity, stop and report to the user with a clear description of the problem before proceeding.
- Never hard-reset (`git reset --hard`) without preserving progress
- Logical, isolated commit grouping (distinct refactors vs. features)
- Commit messages must explain WHY, not just WHAT
- Before composing a commit message, run `git diff --cached | cat` and base the message on that diff only.
- Keep subject concise (<72 chars), imperative, and scoped (e.g., `examples: response_validation`).

### Repository Enforcement (must-follow)
- Stage only the specific files relevant to the change. There may be other changes, check `git status`
- Pre-commit hooks are blocking. If a hook modifies files:
  - Re-stage the exact changed files only
  - Re-run the commit with the SAME commit message (do not alter the message when retrying)
- Prefer TDD for behavioral changes:
  - When practical, add a failing test first; then implement the fix and capture the pass.
  - For docs/formatting and clearly non-functional edits, use common sense—validate with CI instead of adding tests.
- Eliminate duplication immediately. Prefer consolidating tests/code instead of leaving placeholders.
- Test naming and scope:
  - Use focused files (e.g., `tests/test_agent_modules/test_agent_run_id.py`) instead of scattering related assertions
  - Avoid duplicate coverage across files; consolidate instead

### Pre-commit & Staging Discipline (evidence-first)
- Commit the intended, necessary changes. Verify intent with:
  - `git status --porcelain | cat` and `git diff`/`git diff --cached`.
- Pre-commit hooks are authoritative; accept their auto-fixes.
  - If hooks modify files, stage those changes and re-run with the same message.
- Keep commits minimal and scoped; avoid unrelated changes.

## Key References
- `examples/` – v1.x modern usage
- `docs/migration/guide.mdx` – Breaking changes
- `tests/integration/` – Real-world behaviors
- `/docs/` – Framework documentation

## Quick Commands
```bash
find src/ -name "*.py" | grep -v __pycache__ | sort  # Initial structure
make ci                                              # Full validation
uv run pytest tests/integration/ -v                  # Integration tests
```

## Memory & Expectations
- User expects explicit status reporting, test-first mindset, and directness. After any negative feedback or protocol breach, switch to manual approval: present minimal options and wait for explicit approval before changes; re-run Step 1 before and after edits. Update this document first after negative feedback.

## Mandatory Search Discipline
- After changes, aggressively search for and clean up related patterns throughout the codebase.

## End-of-Task Checklist
- All requirements in this document respected
- Minimal, precise diffs; no unrelated edits or dead code
- Documentation and docstrings updated for any changes to behavior/APIs/usage
- No regressions
- Sensible, non-brittle tests; avoid duplicate or root-level tests
- Changes covered by tests (integration/unit or explicit user manual confirmation)
- All tests pass
- Example scripts execute and output as expected
