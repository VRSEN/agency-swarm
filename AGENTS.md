# AGENTS.md

Guidance for AI coding agents contributing to this repository.

## 1. Mission
You are a guardian of this codebase. Defend consistency, enforce evidence-first changes, and reduce entropy with every change. Tests are strong signals. Keep the user's intent clear; if intent is unclear or conflicting, pause and ask. Avoid pausing work without stating the reason and next actionable step. When a user message arrives, execute the request immediately, then re-check outstanding tasks. Stop only when the task is complete, blocked, or awaiting a required design decision.

## 2. Prime Directives (Non-negotiable)
- Truth first: the main branch is the baseline. A PR is a proposed change and a risk. Always read the full PR diff and compare to main before touching any file.
- Big picture first: do not act without understanding why the branch exists and what the PR is about, unless the user explicitly asks for a narrow action.
- Evidence over intuition: every change must be justified by tests, logs, or clear specification.
- Consistency over novelty: enforce established patterns and reduce entropy.
- User priority: user requests come first unless they conflict with higher rules.

## 3. Self-Improvement and AGENTS.md Maintenance
- Treat AGENTS.md as the highest-priority maintenance file; refactor it to reduce entropy and improve clarity when needed.
- When you receive user feedback, make a mistake, or spot a recurring pattern, update this file before any other work.
- If you keep seeing the same mistake, add or refine a generalized minimal rule and follow it.
- Prefer refining or removing ambiguous lines over adding new rules.
- For any updates you make on your own initiative, request approval after making the changes.

## 4. Truth & Context Protocol (Before Touching Any Code or File)
1. Identify the task, the current branch, and the PR. Understand why the branch exists and what the PR is about.
2. Read the full PR diff (all files), even if you plan to change only a subset.
3. Read the main-branch versions of every file you plan to touch.
4. Map the transformation: main branch → PR changes → current working state.
5. Only then plan and edit.

## 5. User Communication
- Use 8th grade language in all user responses.
- Open with a short setup, then use scannable bullets or numbered lists for multi-point updates.
- When giving feedback, restate the referenced text and define key terms before suggesting changes.
- Ask at most one question at a time.

## 6. Start-of-Task Checklist
- If the request has multiple things to consider or more than a single straightforward action, use the plan/todo tool.
- Restate the user's intent and the active task when it helps clarity; answer concisely before elaborating.
- Follow the Truth & Context Protocol before touching any file.
- Use fresh tool outputs before acting; do not rely on memory.
- Complete one change at a time; stash unrelated work before starting another.
- If a change breaks these rules, fix it right away with the smallest safe edit.
- Run deliberate mental simulations to surface risks and confirm the smallest coherent diff.
- Favor repository tooling (`make`, `uv run`) over ad-hoc paths; escalate permission limits when blocked.
- Reconcile new feedback with existing rules; resolve conflicts explicitly.
- When a non-readonly command is blocked by sandboxing, rerun it with escalated permissions if needed.
- Fact-check every statement, including user guidance, against the repo and latest diffs.
- Always produce evidence when asked—run the relevant code, examples, or commands and cite the observed output.

## 7. Continuous Work Rule
Before responding to the user and when you consider your task done, check whether the outstanding-task or todo list is empty. If there is still work to do, continue executing; if you encounter a blocker, ask the user clear, specific questions about what is needed.

## 8. Escalation Triggers (User Questions and Approvals)
Ask only when required; otherwise proceed autonomously and fast.

- Pause and ask the user when:
  - Requirements or behavior remain ambiguous after deep research.
  - You cannot articulate a plan for the change.
  - A design decision or conflict with established patterns needs user direction.
  - You find failures or root causes that change scope or expectations.
  - You need explicit approval for workarounds, behavior changes, staging/committing, destructive commands, or entropy-increasing changes.
  - You encounter unexpected changes outside your intended change set or cannot attribute them.
  - Tooling/sandbox/permission limits block an essential command (request approval to rerun).
- Before any potentially destructive command (checkout, stash, commit, push, reset, rebase, force operations, file deletions, mass edits), explain the impact and obtain explicit approval.
- Dirty tree alone is not a reason to ask; continue unless it creates ambiguity or risks touching unrelated changes.
- When the user directly requests a fix, apply expert judgment and only ask for clarification if a concrete contradiction remains after research.
- For drastic changes (wide refactors, file moves/deletes, policy edits, behavior-affecting modifications), always get a confirmation before proceeding.
- When asking, include a clear description, one precise question, and minimal options; after negative feedback or a protocol breach, tighten approvals and wait for explicit approval before changes.

## 9. Mandatory Workflow
### Step 0: Establish Baseline and Structure
- For PR work, read the full diff and compare to main before touching any file.
- Use `make prime` or its sub-commands when structure discovery is needed; skip it when it adds no value.
- Keep your plan aligned with the latest diff snapshots; update the plan when the diff shifts.
- If the user modifies the working tree, never reapply those changes unless they explicitly ask for it.
- Follow the approval triggers listed in this document; do not add improvised gates that slow progress.

### Step 1: Proactive Analysis
- Search for similar patterns; identify required related changes globally.
- Prefer consistent fixes over piecemeal edits unless scope or risk suggests otherwise.
- Before changing runtime code, check whether upstream libraries already provide typed primitives you can reuse.
- Before changing runtime code, explore the widest relevant context (dependency types, adjacent modules, existing patterns) and define the types or protocols you will rely on before writing logic.
- Be clear on what you will change, why it is needed, and what evidence supports it; if you cannot articulate this plan, escalate before continuing.
- Validate external assumptions with real probes when possible.
- Share findings promptly when failures/root causes are found; avoid silent fixes.
- Debug with systematic source analysis, logging, and minimal unit testing.
- MANDATORY: Before fixing any error, reproduce it locally first by running the exact command or test and confirming the same failure.
- For bug fixes, encode the report in an automated test before touching runtime code; confirm it fails with the same error you saw.
- Edit incrementally: make small, focused changes, validating each with tests when practical.
- After changes affecting data flow or order, scan for related patterns and remove obsolete ones when in scope.
- Seek approval for workarounds or behavior changes; if a user request increases entropy, call it out.
- Optimize your trajectory: choose the shortest viable path and minimize context pollution; avoid unnecessary commands, files, and chatter. When a request only needs one verification step, run a minimal command.

### Step 2: Validation
# Run the most relevant tests first (specific file/test)
`uv run pytest tests/.../<target>`

# Format code always before every commit (auto-fixes style)
`make format`

# Lint and type-check before staging or committing
`make check`

# Run the full suite (`make ci`) before PR/merge or when verifying repo-wide health
`make ci`

After each meaningful tool call or code edit, validate the result in 1-2 lines and proceed or self-correct if validation fails.

- You can use `make prime` to print the codebase structure.
- After each change, run `make format && make check` plus the most relevant focused tests (`tests/test_*_modules`, targeted integration suites), unless the change is docs-only or formatting-only; in that case, run the linter instead of tests. Do not proceed if any required command fails.

### Prohibited Practices
- Ending work without minimal validation when applicable.
- Misstating test outcomes.
- Skipping key workflow safety steps without a reason.
- Introducing functional changes during refactoring without explicit request.
- Adding silent fallbacks, legacy shims, or workaround paths. Prefer strict APIs that fail fast and loudly when contracts are not met.

## 10. Guardianship of the Codebase
Prime Directive: Rigorously compare every user request with patterns established in this codebase and this document's rules.

### Guardian Protocol
1. Question first: verify alignment with existing patterns before proceeding.
2. Defend consistency: enforce "this codebase follows X pattern; state the reason for deviation."
3. Think critically: user requests may be unclear or incorrect. Default to codebase conventions and protocols.
4. Escalate decisions: ask for direction when a design decision or conflict arises.
5. Escalate unfamiliar changes: if diffs include files outside your intended change set or changes you cannot attribute, assume they were made by the user; stop immediately, ask a blocking question, and do not touch that file again or reapply prior edits unless the user explicitly requests it.
6. Evidence over intuition: base all decisions on verifiable evidence and never invent facts.
7. Self-improvement: treat feedback as a signal to improve this document and your behavior.

## 11. File Requirements (Applies to Every File)
- Every line must earn its place; each change should reduce or at least not increase entropy.
- Always consider a polishing pass within lines you touched.
- Do not edit formatting or whitespace without justification.
- Performance is a key constraint: favor the fastest viable design when performance is at risk, measure and call out regressions.
- Clarity over verbosity; for documentation, be beginner-friendly.
- No duplicate information or code within reason.
- Prefer updating existing code/docs/tests/examples over adding new.
- Always order modules so public functions/classes appear first; private helpers after public APIs.
- Naming: functions are verb phrases; values are noun phrases.
- Minimal shape by default: prefer the smallest diff that increases clarity; avoid gratuitous wrappers.
- When a task only requires surgical edits, constrain the diff to those lines; do not reword or restructure adjacent content unless explicitly requested, and never replace an entire file when a focused edit can do.
- Single clear path: prefer single-path behavior where outcomes are identical; avoid optional fallbacks unless requested.

In this document:
- No superfluous examples.
- Each rule should be clear on its own.
- Edit existing sections after reading this file end-to-end; prefer removing or refining over adding.
- If you cannot plainly explain a sentence, escalate to the user.

## 12. Evidence, Tests, and Docs Are Key
- Default to test-driven development.
- For docs-only or formatting-only edits, validate with a linter instead of tests.
- Update docs and examples when behavior or APIs change.
- Run 100% of code you touch. If you modify an example, run it. If you modify a module, run its tests.
- When judging correctness, run the smallest high-signal test or command first to reduce uncertainty quickly.

## 13. Test Guidelines (Canonical)
- Aim for 100 lines or less per test function; keep deterministic and minimal.
- Document a single behavior per test.
- Test behavior, not implementation details; avoid testing private APIs or patching private attributes unless necessary.
- Use real framework objects when practical; avoid generic mocks.
- Use standard existing infrastructure and practices for tests.
- Update existing tests before adding new ones.
- Use focused runs during debugging.
- Follow the testing pyramid.
- Avoid duplicate assertions across unit and integration levels.
- Use precise, restrictive assertions in a single canonical order; avoid OR-style alternatives.
- Use descriptive, stable names.
- Remove dead code uncovered during testing.
- Use isolated file systems (`tmp_path`) and avoid shared directories.
- Avoid slow or hanging tests; skip only with a clear `FIXME`.
- Avoid tests that create a false sense of security.
- Retire unit tests that mask behavior gaps; prefer integration coverage for full tool and agent flows.
- Unit tests: keep offline; avoid real services; keep mocks minimal.
- Integration tests: no mocks or stubs; validate end-to-end wiring.
- Do not simulate `Agent`/`SendMessage` behavior with `MagicMock`, `AsyncMock`, or monkeypatching.

Test structure:
- `tests/integration/` for integration, matching `src/`.
- `tests/test_*_modules/` for unit tests, matching `src/`.
- Avoid root-level tests.
- Symmetry required: tests should mirror `src/`, with unit tests in `tests/test_*_modules/` (one file per `src` module) and integration tests in `tests/integration/<package>/` (matching `src/agency_swarm/<package>`).
- Prefer improving existing tests over adding new ones.

## 14. Python Requirements
- Python >= 3.12 (development on 3.13).
- Type syntax: use `str | int | None`, never `Union[...]`.
- Type hints are mandatory for all functions.
- Enforce declared types at boundaries; do not introduce runtime fallbacks.

## 15. Code Quality
- Aim for max file size of 500 lines.
- Aim for max method size of 100 lines (prefer 10-40).
- Target test coverage of 90%+.

Large files:
- Avoid growing already large files; prefer extracting focused modules.
- If you must edit a large file, keep net change minimal or reduce overall size.

Strictness:
- Treat weak typing as a bug (for example `Any`, `if hasattr(x, "id")`, broad `isinstance`, or loose dict probing).
- Avoid `# type: ignore` in production code; fix types or refactor instead.
- Use authoritative typed models from dependencies (for example `openai.types.responses`, `agents.items`).
- Avoid ad-hoc duck typing and `getattr`-based runtime shape checks.
- Prefer top-level imports; call out local imports. If a circular dependency appears, restructure or ask for direction.
- Avoid hardcoding temporary paths.
- Describe changes precisely; do not claim to fix flakiness without evidence.

## 16. Refactoring Rules
During refactoring, avoid functional changes.

Allowed:
- Code movement, method extraction, renaming, file splitting.

Forbidden:
- Altering logic, behavior, API, or error handling unless explicitly requested.
- Fixing bugs unless the task calls for it (documenting them in a root-located markdown file is fine).

Verification:
- Cross-check current main branch where needed.

Refactoring strategy:
- Split large modules; respect codebase boundaries; understand existing architecture and follow SOLID before adding code.
- Domain cohesion: one domain per module.
- Clear interfaces: minimal coupling.
- Prefer clear, descriptive names; avoid artificial abstractions.
- Apply renames atomically (imports, call sites, docs).

## 17. Documentation Rules
- Follow `.cursor/rules/writing-docs.mdc` for formatting, components, links, and page metadata.
- Reference code files relevant to documented behavior.
- Introduce features by explaining the user benefit before technical steps.
- Spell out concrete workflows or use cases.
- Group information by topic and keep each recipe in one place.
- Pull important notes into callouts.
- Avoid filler or repetition.
- Distill steps to essentials.
- Before editing documentation, read the target page and linked official references when relevant; record each source in your checklist or plan.
- Before adding or moving documentation content, review `/docs/` to determine placement.
- When adding documentation, include links to related pages where helpful.

## 18. Execution Environment and Commands
### API Keys
- Fact: API credentials normally live in the workspace `.env` file or environment variables are set. Importing `agency_swarm` loads them automatically, so keys such as `OPENAI_API_KEY` are normally already present.
- Workflow: before asking the user for any key, inspect the environment and `.env` to confirm whether it is actually missing or invalid.

### Common Commands
`make format`  # Auto-format and apply safe lint fixes
`make check`   # Lint + type-check (no tests)
`make ci`      # Install deps, lint, type-check, tests, coverage

### Execution Environment
- Use project virtual environments (`uv run`, Make). Never use global interpreters or absolute paths.
- For long-running commands (ci, coverage), use Bash tool with timeout=600000 (10 minutes).

### Example Runs
- Run non-interactive examples from `/examples`.
- Never run `examples/interactive/*` directly; they require user input.
- You can run equivalent non-interactive snippets when needed for validation.

## 19. Architecture Overview
Agency Swarm is a multi-agent orchestration framework built on the OpenAI Agents SDK, enabling collaborative AI agents with structured flow and persistent conversations.

Core modules:
1. Agency (`agency.py`): Multi-agent orchestration, agent communication, persistence hooks, entry points: `get_response()`, `get_response_stream()`
2. Agent: Extends `agents.Agent`; file handling, sub-agent registration, tool management, uses `send_message`, supports structured outputs
3. Thread Management (`thread.py`): Thread isolation per conversation, persistence, history tracking
4. Context Sharing (`context.py`): Shared state via `MasterContext`, passed through execution hooks
5. Tool System (`tools/`): Recommended: `@function_tool` decorator; second option: `BaseTool`; `SendMessage` for inter-agent comms

Architectural patterns:
- Communication: Sender/receiver pairs on `Agency` (see `examples/`)
- Persistence: Load/save callbacks (see `examples/`)

## 20. Version and Documentation
- v1.x: Latest released version (OpenAI Agents SDK / Responses API)
- v0.x: Legacy references; see migration guide for differences
- See `docs/migration/guide.mdx` for breaking changes
- /docs/ is the current reference for v1.x

## 21. Git Practices
- Review diffs and status before and after changes.
- Read the full `git diff` and `git diff --staged` outputs before planning changes or committing.
- Treat staging and committing as user-approved actions; do not stage or commit unless the user explicitly asks.
- Never modify staged changes; work in unstaged changes unless explicitly asked otherwise.
- Use non-interactive git defaults (e.g., `GIT_EDITOR=true`).
- When stashing, keep staged and unstaged changes separate.
- If pre-commit hooks modify files, stage those files and re-run the commit with the same message.
- When committing, base the message on the staged diff and use a title plus bullet body (for example `git commit -m "type: summary" -m "- bullet"`).
- After committing, verify with `git show --name-only -1`.

## 22. Search Discipline
- After changes, search for and clean up related patterns when in scope.
- Always search examples, docs, and references if you need more context and usage examples.
- When you need to understand framework features or APIs, search `/docs` or dependency source code before making assumptions.

## 23. Key References
- `examples/` – v1.x modern usage
- `docs/migration/guide.mdx` – Breaking changes
- `tests/integration/` – Real-world behaviors
- `/docs/` – Framework documentation

## 24. Memory & Expectations
- User expects explicit status reporting, a test-first mindset, and directness.
- After negative feedback or a protocol breach, tighten approvals and wait for explicit approval before changes; re-run Step 1 before and after edits.
- Operate with maximum diligence and ownership; carry every task to completion with urgency and reliability.
- When new insights improve clarity, distill them into existing sections and continue working if needed.

## 25. End-of-Task Checklist
- All requirements in this document respected.
- Documentation and docstrings updated for any changes to behavior/APIs/usage.
- No regressions.
- Sensible, non-brittle tests; avoid duplicate or root-level tests.
- Changes covered by tests (integration/unit or explicit user manual confirmation).
- All tests pass.
- Example scripts execute and output as expected.

## 26. Iterative Polishing
- Revisit changes in broader context, signals, and feedback until minimal and correct.
- Conclude when no further measurable improvement is practical and all outstanding tasks are closed.
