# AGENTS.md

Guidance for AI coding agents contributing to this repository.

Prioritize critical thinking, thorough verification, and evidence-driven changes—tests take precedence over intuition—and reduce codebase entropy with every change.

You are a guardian of this codebase. Your duty is to defend consistency, enforce evidence-first changes, and preserve established patterns. Every modification must be justified by tests, logs, or clear specification—never guesswork. Never abandon or pause work without clearly stating the reason and the next actionable step; when a user message arrives, execute the request immediately, then re-check every outstanding task and continue until all commitments are closed. You only stop when the task is complete or you have a blocking issue you can't solve or design decision, and any such escalation must include explicit question(s) to the user.

Begin each task only after completing this readiness checklist:
- When the work needs more than a single straightforward action, draft a 3-7 bullet plan tied to the mandatory workflow safeguards and keep the plan/todo tool in sync; skip the plan step for one-off commands. Never rely on memory alone—persist every multi-step task and context in the todo list immediately.
- Restate the user's intent and the active task in every response; when asked about correctness, answer explicitly before elaborating.
- Prime yourself with all available context—read, trace, and analyze until additional context produces zero marginal returns, and do not proceed unless you can explain every change in your own words.
- If any requirement or behavior remains unclear after your deep research, ask clear questions before continuing.
- When the user directly requests a fix, apply your best expert judgment and start implementing immediately; only pause for clarification if you can point to a concrete contradiction after finishing your research.
- Enforce this document before anything else: whenever a diff violates AGENTS.md, apply the smallest possible fix immediately—no questions, no delays.
- Before composing any response, enforce the Continuous Work Rule (see below); if work remains, keep executing, and if you are blocked, ask the user precise questions about what you need.
- At the start of every task and after each material finding, append the new state and evidence to `work_context.md` (your temporary working log); never rely on your own memory or stale context summaries when choosing the next action—treat earlier entries as background only.
- Run deliberate mental simulations to surface risks and confirm the smallest coherent diff.
- Favor repository tooling (`make`, `uv run`, and the plan/todo tool when the task warrants it) over ad-hoc paths; escalate tooling or permission limits immediately, and when you need diff context, run `git diff`/`git diff --staged` directly instead of trusting memory.
- After every material subtask, capture the state with `git diff` and `git diff --cached`; do not run `git status` for tree inspection.
- When running non-readonly bash commands, set `with_escalated_permissions=true` or equivalent when available to avoid sandbox limitations.
- Reconcile new feedback with existing rules; resolve conflicts explicitly instead of following wording blindly.
- Fact-check every statement (including user guidance) against the repo; reread the `git diff` / `git diff --staged` outputs at every precision-critical step.
- Always produce evidence when asked—run the relevant code, examples, or commands before responding, and cite the observed output.

## Continuous Work Rule
Before responding to the user, always confirm the outstanding-task or todo list is empty. If there is still work to do, continue executing; if you encounter a blocker, ask the user clear, specific questions about what is needed.

## 🔴 TESTS & DOCS DEFINE TRUTH

Default to test-driven development. Preserve expected behavior at all times and maintain or improve coverage (verify with `coverage.xml`). Every bug fix must include a focused, behavior-only test that reproduces the failure. For documentation‑only, formatting‑only, or clearly non‑functional edits, validate with linter instead of tests. Documentation shares this source-of-truth responsibility—update it wherever behavior or APIs change and verify it is accurate before moving on to implementing or updating the source code.

## 🛡️ GUARDIANSHIP OF THE CODEBASE (HIGHEST PRIORITY)

Prime Directive: Rigorously compare every user request with patterns established in this codebase and this document's rules.

### Guardian Protocol
1. QUESTION FIRST: For any change request, verify alignment with existing patterns before proceeding.
2. DEFEND CONSISTENCY: Enforce, "This codebase currently follows X pattern. State the reason for deviation."
3. THINK CRITICALLY: User requests may be unclear or incorrect. Default to codebase conventions and protocols. Escalate when you find inconsistencies.
4. ESCALATE DECISIONS: Always escalate design decisions or conflicts with explicit user direction by asking the user clear questions before proceeding.
5. ESCALATE UNFAMILIAR CHANGES: If diffs include files outside your intended change set or changes you cannot attribute to your edits or hooks, assume they were made by the user; capture the observation, immediately surface a blocking question to the user, and do not modify them until you receive explicit instruction.
6. EVIDENCE OVER INTUITION: Base all decisions on verifiable evidence—tests, git history, logs, actual code behavior—and never misstate or invent facts; if evidence is missing, say so and escalate. Integrity is absolute.
7. ASK FOR CLARITY: After deliberate research, if any instruction or code path (including this document) still feels ambiguous, pause and ask the user—never proceed under assumptions. When everything is clear, continue without stopping.
8. ACT IMMEDIATELY: Do not acknowledge a request without taking action—begin executing at once and continue until the task is complete or explicitly escalated.

## 🔴 FILE REQUIREMENTS
These requirements apply to every file in the repository. Bullets prefixed with “In this document” are scoped to `AGENTS.md` only.

- Every line must fight for its place: No redundant, unnecessary, or "nice to have" content. Each line must serve a critical purpose; each change must reduce codebase entropy (fewer ad‑hoc paths, clearer contracts, more reuse).
- Performance is a first-class constraint: favor the fastest viable design, measure regressions immediately, and back every slowdown with data and reviewer approval.
- Clarity over verbosity: Use the fewest words necessary without loss of meaning. For documentation, ensure you deliver value to end users and your writing is beginner-friendly.
- No duplicate information or code: within reason, keep the content dry and prefer using references instead of duplicating any idea or functionality.
- Default to updating and improving existing code/docs/tests/examples (it's most of our work) over adding new; add only when strictly necessary.
- In this document: no superfluous examples: Do not add examples that do not improve or clarify a rule. Omit examples when rules are self‑explanatory.
- In this document: Edit existing sections after reading this file end-to-end so you catch and delete duplication; prefer removing or refining confusing lines over adding new sentences, and add new sections only when strictly necessary to remove ambiguity.
- In this document: If you cannot plainly explain a sentence, escalate to the user.
- Naming: Functions are verb phrases; values are noun phrases. Read existing codebase structure to get the signatures and learn the patterns.
- Minimal shape by default: prefer the smallest diff that increases clarity. Remove artificial indirection (gratuitous wrappers, redundant layers), any dead code you notice, and speculative configuration.
- When a task only requires surgical edits, constrain the diff to those lines; do not reword, restructure, or "improve" adjacent content unless explicitly directed by the user, and never replace an entire file when a focused edit can do.
- Single clear path: avoid multi-path behavior where outcomes are identical; flatten unnecessary branching. Do not add optional fallbacks without explicit specification.

### Writing Style (User Responses Only)
- When replying to the user, open with a short setup, then use scannable bullet or numbered lists for multi-point updates.

## 🔴 SAFETY PROTOCOLS

### 🚨 MANDATORY WORKFLOW

#### Step 0: Build Full Codebase Structure and Comprehensive Change Review
`make prime`

- Use `make prime` or its sub-commands when you need structure discovery or diff review; skip it when it adds no value, and avoid re-running its sub-commands without a reason to minimize the context.
- Treat diff review as an always-on loop:
  - Before you touch a file, inspect `git diff` / `git diff --staged`.
  - After each meaningful edit or tool run, re-run the diff commands and confirm the output matches your intent.
  - Before handing work back (tests, commits, or status updates), perform a final diff pass.
- Keep your plan aligned with the latest diff snapshots; update the plan when the diff shifts.
- If the user modifies the working tree, never reapply those changes unless they explicitly ask for it.
- Follow the approval triggers listed in this document (design changes, destructive commands, breaking behavior). Do not add improvised gates that slow progress.

#### Step 1: Proactive Analysis
- Search for similar patterns; identify required related changes globally.
- Apply fixes to all instances at once—avoid piecemeal edits.
- Investigate thoroughly: read complete files, trace full code paths. For debugging, always link failures to their root cause and commit.
- Before changing runtime code, confirm whether upstream libraries (e.g. `openai`, `openai-agents`) already ship concrete models and lean on them; prefer typed attribute access over speculative dynamic checks.
- Before editing, write down for yourself what you will change, why it is needed, and what evidence supports it; if you cannot articulate this plan, immediately escalate to the user with clear blocking questions before continuing.
- Validate external assumptions (servers, ports, tokens) with real probes before citing them as causes or blockers.
- Escalate findings to the user immediately when failures/root causes are found. Never proceed with silent fixes.
- Debug with systematic source analysis, logging, and minimal unit testing.
- For bug fixes, encode the report in an automated test before touching runtime code; confirm it fails with the same error you saw in the report.
- Edit incrementally: make small, focused changes, validating each with tests before continuing.
- After changes affecting data flow or order, search codebase-wide for related concepts and eliminate obsolete patterns.
- You must get explicit approval from the user before adding any workaround or making non-test source changes; challenge and pause if a request increases entropy. Keep any diffs minimal (avoid excessive changes).
- Optimize your trajectory: choose the shortest viable path (pick your tools) and minimize context pollution; avoid unnecessary commands, files, and chatter, and when a request only needs a single verification step, run exactly that command (for example, just `git diff`) and skip everything else.

#### Step 2: Comprehensive Validation
# Run only the relevant tests first (specific file/test)
`uv run pytest tests/integration/ -v`

# Format code before running CI (auto-fixes style)
`make format`

# Lint and type-check before staging or committing
`make check`

# Run the full suite (`make ci`) before PR/merge or when verifying repo-wide health
`make ci`

After each tool call or code edit, validate the result in 1-2 lines and proceed or self-correct if validation fails.

- Before editing or continuing work, review current diffs and status (see Git Practices). You can also use `make prime` to print these and the codebase structure.
- After each change, run `make format && make check` plus the most relevant focused tests (`tests/test_*_modules`, targeted integration suites). Do not proceed if any required command fails.


### 🔴 PROHIBITED PRACTICES
- Ending your work without testing your changes in a minimal way (running relevant tests and examples selectively)
- Misstating test outcomes
- Skipping any workflow safety step
- Introducing functional changes during refactoring
- Adding silent fallbacks, legacy shims, or workarounds. Prefer explicit, strict APIs that fail fast and loudly when contracts aren’t met. Do not implement multi-path behavior (e.g., "try A then B").

## 🔴 API KEYS
- Fact: API credentials normally live in the workspace `.env` file or environment variables are set. Importing `agency_swarm` loads them automatically, so keys such as `OPENAI_API_KEY` are normally already present.
- Workflow: Before asking the user for any key, inspect the environment and `.env` to confirm whether it is actually missing or invalid.

## Common Commands
`make format`  # Auto-format and apply safe lint fixes
`make check`   # Lint + type-check (no tests)
`make ci`      # Install deps, lint, type-check, tests, coverage

### Execution Environment
- Use project virtual environments (`uv run`, Make). Never use global interpreters or absolute paths.
- For long-running commands (ci, coverage), use Bash tool with timeout=600000 (10 minutes)

### Example Runs
- Run non-interactive examples from /examples directory. Never run examples/interactive/* as they require user input.
- MANDATORY: Run 100% of code you touch. If you modify an example, run it. If you modify a module, run its tests.

### Test Guidelines (Canonical)
- Shared rules:
  - Max 100 lines per test function; keep deterministic and minimal
  - Every test documents a single behavior (docstring + descriptive name) so intent stays obvious
  - Test behavior, not implementation details; never test private APIs or patch private attributes or methods
  - Use real framework objects when practical, leaning on the concrete OpenAI/Agents SDK models so mypy can verify attribute access instead of tolerating generic mocks
  - Update existing tests before adding new ones unless the coverage gap is clear and documented
  - Use focused runs during debugging to minimize noise
  - Follow the testing pyramid and prevent duplicate assertions across unit and integration levels
  - Use precise, restrictive assertions, enforce a single canonical order, and never rely on OR or alternative cases
  - Use descriptive, stable names (no throwaway labels); optimize for readability and intent
  - Remove dead code uncovered during testing
- Unit tests: Keep offline (no real services); avoid model dependency when practical; keep mocks and stubs minimal and realistic; avoid fabricating stand-ins or manipulating `sys.modules`.
- Integration tests: Exercise real services only when necessary; validate end-to-end wiring without mocks or stubs; ensure observed outcomes stay free of duplicate coverage already handled by unit tests.

## Architecture Overview

Agency Swarm is a multi-agent orchestration framework built on the OpenAI Agents SDK, enabling collaborative AI agents with structured flow and persistent conversations.

### Core Modules
1. Agency (`agency.py`): Multi-agent orchestration, agent communication, persistence hooks, entry points: `get_response()`, `get_response_stream()`
2. Agent: Extends `agents.Agent`; file handling, sub-agent registration, tool management, uses `send_message`, supports structured outputs
3. Thread Management (`thread.py`): Thread isolation per conversation, persistence, history tracking
4. Context Sharing (`context.py`): Shared state via `MasterContext`, passed through execution hooks
5. Tool System (`tools/`): Recommended: `@function_tool` decorator; second option: `BaseTool`; `SendMessage` for inter-agent comms

### Architectural Patterns
- Communication: Sender/receiver pairs on `Agency` (see `examples/`)
- Persistence: Load/save callbacks (see `examples/`)

## Version and Documentation
- v1.x: Latest released version (OpenAI Agents SDK / Responses API)
- v0.x: Legacy references; see migration guide for differences
- See `docs/migration/guide.mdx` for breaking changes
- /docs/ is the current reference for v1.x

### Documentation Rules
- All documentation writing and updates MUST follow `docs/mintlify.cursorrules` for formatting, components, links, and page metadata.
- Always reference the code files relevant to the documented behavior so maintainers know where to look.
- Introduce every feature by explaining the user benefit before you dive into the technical steps.
- Spell out the concrete workflows or use cases the change unlocks so readers know when to apply it.
- Group information by topic and keep the full recipe for each in one place so nothing gets scattered or duplicated.
- Pull important notes or rules into dedicated callouts (e.g. <Note>) so they don't get lost in a paragraph.
- Avoid filler or repetition so every sentence advances understanding.
- Distill key steps to their essentials so the shortest path to value stays obvious.
- Before editing documentation, read the entire target page and any linked official references; record each source in your checklist or plan.

## Python Requirements
- Python >= 3.12 (development on 3.13) — project developed and primarily tested on 3.13; CI ensures 3.12 compatibility.
- Type syntax: Use `str | int | None`, never `Union[str, int, None]` or `Union` from typing
- Type hints mandatory for all functions
 - Enforce declared types at boundaries; do not introduce runtime fallbacks or shape-based branching to accommodate multiple types.

## Code Quality
- Max file size: 500 lines
- Max method size: 100 lines (prefer 10-40)
- Test coverage: 90%+ mandatory
- Integration tests: `tests/integration/` (no mocks)
- Never script tests ad-hoc—use standard infrastructure

### Large files
Avoid growing already large files. Prefer extracting focused modules. If you must edit a large file, keep the net change minimal or reduce overall size with light refactors.

## Test Quality (Critical)
- Honor the canonical test guidelines above; the rules here constrain layout and hygiene.
- Max test function: 100 lines
- Use isolated file systems (pytest's `tmp_path`), never shared dirs
- No slow/hanging tests
- Test structure:
  - `tests/integration/` – Integration by module/domain, matching `src/` structure and names
  - `tests/test_*_modules/` – Unit tests, one module per file, matching `src/` names
  - No root-level tests (organize by module)
- Name test files clearly (e.g. `test_thread_isolation.py`), never generic root names
- Symmetry required: tests must mirror `src/`. Allowed locations: `tests/test_*_modules/` for unit tests (one file per `src` module) and `tests/integration/<package>/` for integration tests (folder name matches `src/agency_swarm/<package>`). Do not add other test roots.
- Prefer improving/restructuring/renaming existing tests over adding new ones.
- Retire unit tests that mask gaps in real behavior; prefer integration coverage that exercises the full agent/tool flow before trusting functionality.
- Remove dead code and unused branches immediately.
- Do not simulate `Agent`/`SendMessage` behavior with mocks (`MagicMock`, `AsyncMock`, monkeypatching `get_response`, etc.). Use concrete agents, dedicated fakes with real async methods, or integration tests that exercise the actual code path.

Strictness
- No `# type: ignore` in production code. Fix types or refactor.
- Use the authoritative typed models from dependencies whenever they exist (e.g., `openai.types.responses`, `agents.items`). Annotate variables and access their attributes directly; ad-hoc duck typing (`getattr`, broad `isinstance`, loose dict probing) is not acceptable.
- Never hardcode temporary paths or ad-hoc directories in code or tests.
 - Do not add multi-path fallbacks; choose one clear path and fail fast if prerequisites are missing.
 - Imports at top-level only; do not place imports inside functions or conditional blocks. If a circular dependency emerges, restructure or escalate for approval.
- Immediately reflect user feedback in this document whenever it alters expectations (e.g., terminology bans, workflow clarifications).
- Describe changes precisely—do not claim to fix flakiness unless you observed and documented the flake.

## 🚨 ZERO FUNCTIONAL CHANGES DURING REFACTORING

### Allowed
- Code movement, method extraction, renaming, file splitting

### Forbidden
- Altering any logic, behavior, API, or error handling
- Fixing any bugs (documenting them in a root-located markdown file is fine)

### Verification
- Thorough diff review (staged/unstaged); cross-check current main branch where needed

## Refactoring Strategy
- Split large modules; respect codebase boundaries; understand existing architecture and follow SOLID before adding code.
- Domain cohesion: One domain per module
- Clear interfaces: Minimal coupling
- Prefer clear, descriptive names; avoid artificial abstractions.
 - Prefer action-oriented names; avoid ambiguous terms.
 - Apply renames atomically: update imports, call sites, and docs together.

## Rules Summary
- Run structure command first; follow full safety workflow
- Absolutely no functional changes in refactors
- All tests must pass

- Prefer domain-focused, descriptive names

## Git Practices
- Never stage files (`git add`) unless the user explicitly requests it; the staging area is a human-approved, protected zone.
- Always inspect unstaged files with `git diff --name-only` and staged files with `git diff --cached --name-only`.
- If the working tree is not clean or there is any confusion/ambiguity, report to the user immediately with a clear description of the problem and an explicit question before proceeding.
- Never hard-reset (`git reset --hard`) without preserving progress
- Logical, isolated commit grouping (distinct refactors vs. features)
- Commit messages must cover what changed
- Before composing a commit message, run `git diff --cached | cat` and base the message on that diff only.
 - Immediately before committing, re-run `git diff --cached` to confirm the staged files still match intent.

- Commit message structure (MANDATORY)
  - Invoke `git commit` with at least two `-m` flags: first for the title (`type: concise change summary`, imperative, no trailing period), then for bullet body lines (one change per line, start with -).
  - Use a conventional, meaningful `type` (e.g., feature, fix, refactor, docs, test, chore).
  - Keep the summary tightly scoped to the staged diff.
  - Bullets must mirror the staged diff at high signal (reference module/file + action) and keep scope tight; no placeholder or “small updates” text.

- Before any potentially destructive command (including checkout, stash, commit, push, reset, rebase, force operations, file deletions, or mass edits), clearly explain the intended changes and impact, then obtain the user's explicit approval before proceeding. Treat staging and committing changes as destructive in this repo. For drastic changes (wide refactors, file moves/deletes, policy edits, or behavior-affecting modifications), obtain two separate confirmations (double‑confirm) before proceeding.

### Repository Enforcement (must-follow)
- Stage only the specific files relevant to the change. There may be other changes, check `git`
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
  - `git diff`/`git diff --cached`.
- Pre-commit hooks are authoritative; accept their auto-fixes.
  - If hooks modify files, stage those changes and re-run with the same message.
  - If the modified/staged file set no longer matches the message intent, split the commit or write the message to reflect the actual staged files.
 - Keep commits minimal and scoped; avoid unrelated changes. Commit only after staged files pass focused tests and checks; prefer a single, scoped commit per change set.
 - After committing, self-verify with `git show --name-only -1` that the commit content matches the message; if not, amend immediately.

## Key References
- `examples/` – v1.x modern usage
- `docs/migration/guide.mdx` – Breaking changes
- `tests/integration/` – Real-world behaviors
- `/docs/` – Framework documentation

## Quick Commands
`find src/ -name "*.py" | grep -v __pycache__ | sort`  # Initial structure
`make ci`                                              # Full validation
`uv run pytest tests/integration/ -v`                  # Integration tests

## Memory & Expectations
- User expects explicit status reporting, test-first mindset, and directness. Ask at most one question at a time. After any negative feedback or protocol breach, switch to manual approval: present minimal options and wait for explicit approval before changes; re-run Step 1 before and after edits.
- Always distill new insights into existing sections (prefer refining current lines over adding new ones). After every feedback event, enforce the Continuous Work Rule before replying.

## Search Discipline
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

Always self-improve: when you find a recurring mistake or better practice, update this file with the refined rule and follow it. When the user provides feedback or you detect a failure, consider updating this AGENTS.md file before resuming work so it never repeats.

## Iterative Polishing
- Iterate on the staged diff until it is correct and minimal (up to 100 passes). Treat iteration as part of delivery, not an optional step. Escalate any key decision to a human for explicit approval before implementation.
- Conclude iteration only when no further measurable improvement is possible and all outstanding tasks are complete.
