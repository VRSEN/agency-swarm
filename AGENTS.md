# AGENTS.md

Guidance for AI coding agents contributing to this repository. Prioritize critical thinking, thorough verification, evidence-driven zero-fluff deliverables, and polished outputs that reduce entropy with every change. Documentation is a core product—treat users as the top priority.

## Purpose & Mindset
- Guardian first: defend existing patterns and rules, default to tests/logs/specs, and escalate conflicts immediately.
- No assumptions or hallucinations: if any term or instruction is unclear, stop, investigate the repo and `work_context.md`, and ask the user if unresolved—unknowns are blockers.
- Full commitment to users and docs: write only user-unblocking content from the start and preserve required details (including diagrams); mirror Mentify/Lovable clarity.
- Integrate feedback immediately and work autonomously until everything is 100% clear—even if it takes many iterations; log doubts and resolutions in `work_context.md`.
- Restate the user’s intent and active task in every response; answer correctness prompts explicitly before elaborating.
- Act immediately on requests; never pause without an actionable reason; escalate blockers with a specific question.
- Treat this file as your playbook—self-improve relentlessly without losing information.

## Writing Style (User Responses)
- When replying to the user, open with a short setup, then use scannable bullet or numbered lists for multi-point updates.

## Readiness & Logging
- For any task beyond a single straightforward action, draft a 3–7 bullet plan with the plan/todo tool and keep it in sync; never rely on memory for multi-step work.
- Prime context before edits: read relevant files end-to-end, trace code paths, and do not proceed until you can explain each change in your own words.
- Record the current state at task start and after every material finding in `work_context.md`; treat earlier entries as background only.
- Run deliberate mental simulations to surface risks and choose the smallest coherent diff; enforce this document before anything else.
- Diff discipline: before touching files and after each material edit/tool run, inspect `git diff` and `git diff --staged`; capture snapshots after each subtask and avoid `git status` for tree inspection.
- Favor repository tooling (`make`, `uv run`, plan/todo tool); if a shell command is non-readonly, set `with_escalated_permissions=true` when available.
- Continuous Work Rule: do not respond until tasks are complete; if blocked, state the blocker and ask one precise question.
- When the user asks for a fix, begin implementation immediately after research unless a concrete contradiction appears; reconcile new feedback with existing rules explicitly.
- After any user feedback, pause to integrate it into your plan and rules; if anything is unclear, ask immediately.
- Fact-check every statement against the repo; produce evidence (commands/logs/tests) whenever asked.

## Workflow Safeguards
### Step 0: Structure & Diff Review
- Run `make prime` when you need structure discovery or consolidated diff review; avoid rerunning without purpose.
- Keep a diff loop always on: inspect `git diff`/`git diff --staged` before edits, after each meaningful change or tool run, and before handoff; keep your plan aligned with the latest diff.
- Never reapply user-made changes unless explicitly requested; follow approval triggers for design changes, destructive commands, or behavior-breaking edits.

### Step 1: Proactive Analysis
- Search for similar patterns and fix all instances together.
- Read complete files and trace full code paths; prefer typed upstream models (e.g., `openai`, `openai-agents`) over speculative checks.
- Write down what you will change, why, and the evidence; if you cannot, escalate with clear blocking questions.
- Validate external assumptions with real probes before citing them.
- Surface failures/root causes to the user immediately; no silent fixes.
- Debug with systematic source analysis, logging, and minimal tests.
- For bug fixes, add a failing test first, then implement the fix and capture the pass.
- Edit incrementally with tests after each change.
- After data-flow/order changes, sweep the codebase for related concepts and remove obsolete patterns.
- Seek explicit approval before adding workarounds or non-test source changes; keep diffs minimal and avoid excess commands.
- Optimize for the shortest viable path; run only the commands necessary for the current verification.

### Step 2: Comprehensive Validation
- Run targeted tests first (`uv run pytest tests/integration/ -v` or narrower).
- Format before CI: `make format`; lint/type-check: `make check`; full suite: `make ci`.
- After each command, note the result, fix failures immediately, and do not proceed if a required command fails.
- Before continuing edits, review current diffs; after changes, run `make format && make check` plus the most relevant focused tests.

### Prohibited Practices
- Ending work without running relevant tests/examples.
- Misstating test outcomes or skipping workflow safeguards.
- Introducing functional changes during refactoring.
- Adding silent fallbacks, legacy shims, or multi-path behavior when outcomes are identical.

## Guardian Protocol
Prime Directive: rigorously compare every request to codebase patterns and these rules.
1. QUESTION FIRST: verify alignment before proceeding.
2. DEFEND CONSISTENCY: state any deviation from existing patterns.
3. THINK CRITICALLY: default to conventions; escalate inconsistencies.
4. ESCALATE DECISIONS: ask clear questions before design shifts.
5. ESCALATE UNFAMILIAR CHANGES: if diffs touch unknown files or changes you did not make, assume user edits; report and pause.
6. EVIDENCE OVER INTUITION: rely on verifiable proof; escalate if missing.
7. ASK FOR CLARITY: never proceed under ambiguity.
8. ACT IMMEDIATELY: start executing once clear; continue until complete or escalated.

## Documentation Discipline (Mintlify/Lovable)
- Documentation is a core product—write zero-fluff, user-unblocking content from the start and follow `docs/mintlify.cursorrules`.
- Read the entire target page and linked official references before editing; record sources in your checklist or plan.
- Reference the relevant code files; explain user benefit first, then concrete workflows/use cases with the full recipe in one place.
- List prerequisites/env vars up front and put the first runnable snippet/command within the first screen; keep steps tighter than prose.
- Use Mintlify components (tabs, accordions, cards) and diagrams (including Mermaid) when they clarify flows—never as filler; preserve required diagrams.
- Use callouts for important notes; warnings/troubleshooting only for real, observed failure modes.
- Replace marketing language with concise answers to: What is this? So what (why it matters)? Now what (specific next step)?
- Avoid duplication and filler; distill each step to the shortest path to value; link to supporting URLs when they help the user.

**Lovable lessons (max 5):**
1. Lead with action: surface a runnable snippet/command immediately; keep intros short.
2. Keep sections scannable with clear headings and ordered steps; prefer compact lists over narrative.
3. State prerequisites and expected outcomes before steps; anchor links to supporting docs where helpful.
4. Provide real, runnable examples early and keep them minimal.
5. Use focused callouts/components for clarifications and FAQs; cut any text that doesn’t move the user forward.

## Project Knowledge
### Architecture Overview
1. Agency (`agency.py`): multi-agent orchestration; entry points `get_response()`, `get_response_stream()`.
2. Agent: extends `agents.Agent`; file handling, sub-agent registration, tools, `send_message`, structured outputs.
3. Thread Management (`thread.py`): per-conversation isolation, persistence, history.
4. Context Sharing (`context.py`): shared state via `MasterContext`.
5. Tool System (`tools/`): prefer `@function_tool`; `BaseTool` alternative; `SendMessage` for inter-agent comms.

### Architectural Patterns
- Communication: sender/receiver pairs on `Agency` (see `examples/`).
- Persistence: load/save callbacks (see `examples/`).

### Version and Documentation
- v1.x: latest release (OpenAI Agents SDK / Responses API); v0.x legacy—see migration guide.
- `docs/migration/guide.mdx` lists breaking changes; `/docs/` is the reference for v1.x.

## Key References
- `examples/` – v1.x modern usage.
- `docs/migration/guide.mdx` – breaking changes.
- `tests/integration/` – real-world behaviors.
- `/docs/` – framework documentation.

## Code & Test Quality
### Tests & Docs Define Truth
- Default to TDD; preserve expected behavior and coverage (90%+; check `coverage.xml`).
- Every bug fix gets a focused, behavior-only failing test before the fix.
- For docs/formatting-only work, validate with linter instead of tests; docs share source-of-truth responsibility.

### Code/File Requirements
- Every line must earn its place: reduce entropy, favor performance, and keep clarity over verbosity.
- No duplication; default to updating existing code/docs/tests/examples; add only when necessary.
- Order modules with public APIs first, private helpers (prefixed `_`) after.
- Naming: functions are verb phrases; values are noun phrases.
- Minimal shape: avoid unnecessary indirection, dead code, speculative config; prefer surgical edits and a single clear path with no redundant branching.
- When a task is surgical, constrain the diff to required lines; never replace whole files without need.
- In this document: no superfluous examples; edit existing sections after reading end-to-end; if a sentence is unclear, escalate.

### Quantitative Limits
- Max file size: 500 lines; max method: 100 lines (prefer 10–40).
- Test coverage: 90%+ required.
- Integration tests live in `tests/integration/` (no mocks); never script tests ad hoc.

### Large Files
- Avoid growing already large files; extract focused modules or reduce size when touching them.

### Test Quality & Structure
- Max test function 100 lines; deterministic and minimal.
- One behavior per test with docstring + descriptive name; test behavior, not implementation details; avoid testing private APIs.
- Use real framework objects when practical; avoid generic mocks of Agent/SendMessage (no `MagicMock`, `AsyncMock`, or monkeypatching `get_response`); use concrete agents or dedicated fakes with real async methods.
- Update existing tests before adding new ones unless a clear coverage gap exists.
- No slow or hanging tests; favor isolated, fast runs.
- Use precise assertions and a single canonical order; no OR/alternative cases.
- Use descriptive, stable names; remove dead code and unused branches.
- Use isolated file systems (pytest `tmp_path`), never shared dirs.
- Test locations: `tests/test_*_modules/` mirroring `src/` for unit tests; `tests/integration/<package>/` mirroring `src/agency_swarm/<package>` for integration; no root-level tests; one module per file for unit tests; avoid duplicate coverage.
- Prefer integration coverage that exercises full agent/tool flow; retire unit tests that mask gaps.
- Follow the testing pyramid; avoid duplicate assertions across unit and integration levels.

### Strictness
- No `# type: ignore` in production code; fix types or refactor.
- Use authoritative typed models from dependencies; use direct attribute access, not duck typing (`getattr`, broad `isinstance`, dict probing).
- Never hardcode temporary paths or ad-hoc dirs.
- No multi-path fallbacks; choose one clear path and fail fast if prerequisites are missing.
- Imports at top-level only; fix circular deps by restructuring or escalate for approval.
- Reflect user feedback in this document whenever expectations change.
- Describe changes precisely; do not claim to fix flakiness without evidence.

### Python & Execution
- Python >= 3.12 (develop on 3.13; CI ensures 3.12).
- Type hints mandatory; use `str | int | None` style.
- Use project virtual environments (`uv run`, Make); never global interpreters/absolute paths.
- For long-running commands (e.g., CI/coverage), use the Bash tool with timeout 600000ms.

### Example Runs
- Run non-interactive examples from `/examples`; never run `examples/interactive/*`.
- Run 100% of code you touch: if you modify an example, run it; if you modify a module, run its tests.

### Zero Functional Changes During Refactoring
- Allowed: code movement, method extraction, renaming, file splitting.
- Forbidden: altering logic/behavior/API/error handling or fixing bugs.
- Verification: thorough diff review (staged/unstaged); cross-check main branch when needed.

### Refactoring Strategy
- Split large modules, respect boundaries, and follow SOLID.
- Domain cohesion: one domain per module; minimal coupling and clear interfaces.
- Prefer action-oriented, descriptive names; apply renames atomically across imports/call sites/docs.

## Git & Change Control
- Never stage files unless the user explicitly requests; respect existing staged changes.
- Inspect unstaged files with `git diff --name-only` and staged with `git diff --cached --name-only`; if the tree is unclear, describe it to the user and ask before proceeding.
- Never hard-reset; before rebase/history edits set `GIT_EDITOR=true`.
- Group commits logically (distinct refactors vs features); commit messages must cover what changed.
- Treat staging/committing/pushing/resetting as destructive; explain impact and obtain explicit approval first. For wide refactors/file moves/policy edits/behavior changes, double-confirm.
- Do not reapply user changes without request.

### Repository Enforcement
- Stage only files relevant to the change.
- Pre-commit hooks are blocking; if hooks modify files, re-stage exactly those files and re-run with the same message.
- Prefer TDD for behavioral changes; for docs/formatting/non-functional edits, validate with CI.
- Eliminate duplication immediately; consolidate tests/code instead of leaving placeholders.
- Test naming/scope: focused files (e.g., `tests/test_agent_modules/test_agent_run_id.py`), avoid scattered assertions, avoid duplicate coverage.

### Pre-commit & Staging Discipline
- Commit intent matches staged diff; verify with `git diff`/`git diff --cached`.
- Accept hook auto-fixes; if the staged set changes the message intent, split or adjust the message accordingly.
- Do not commit until `make format` and `make check` pass; if format changes files, stage them before commit.
- Keep commits minimal/scoped; after committing, verify with `git show --name-only -1`; amend only if mismatched.
- Commit message structure (MANDATORY):
  - Run `git commit -m "<type: concise change summary>" -m "- <bullet>"...`
  - Use conventional types (feature, fix, refactor, docs, test, chore); keep scope tight.

## Environment, Commands, and Keys
- API keys: usually from `.env` or environment; importing `agency_swarm` loads them. Before asking for keys, inspect the environment/`.env` to confirm they are missing or invalid.
- Common commands: `make format`, `make check`, `make ci`.
- Quick commands: `find src/ -name "*.py" | grep -v __pycache__ | sort`; `uv run pytest tests/integration/ -v`.
- Use `make ci` for full validation; use `make prime` for structure/diff context.

## Search & Memory
- User expects explicit status, test-first mindset, and directness; ask at most one question at a time. After negative feedback or protocol breaches, switch to manual approval: present minimal options and wait for approval; re-run Step 1 before/after edits.
- Always distill new insights into existing sections (refine instead of adding). After every feedback event, enforce the Continuous Work Rule before replying.
- If context is unclear, stop and clarify: trace the repository first; if reliable info requires it, run targeted web search using an Agents SDK WebSearchTool; if still unclear, confirm details with the user.

## End-of-Task & Polishing
- End-of-task checklist: all rules followed; minimal, precise diffs with no unrelated edits/dead code; docs/docstrings updated for behavior/API changes; no regressions; sensible non-brittle tests without duplicates; changes covered by tests or explicit user confirmation; all tests pass; examples you touched run and output as expected.
- Before responding, re-read the current diff to ensure clarity and that no requested or previously present details were dropped while compressing; polish wording/layout to match repo patterns.
- Iterate on the diff using feedback signals (`git diff`/tests/logs) until changes are correct, minimal, and globally optimal; escalate key decisions as needed; finish only when every outstanding task is closed.
- Always self-improve: when you find a recurring mistake or better practice, update this file accordingly.
