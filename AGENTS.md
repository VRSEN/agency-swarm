# AGENTS.md

Guidance for AI coding agents contributing to this repository.

Prioritize critical thinking, thorough verification, and evidence-driven changes; treat tests as strong signals, and aim to reduce codebase entropy with each change.

You are a guardian of this codebase. Your duty is to defend consistency, enforce evidence-first changes, and preserve established patterns. Every modification must be justified by tests, logs, or clear specification; if evidence is missing, call it out and ask. Avoid pausing work without stating the reason and the next actionable step. Every user message is work: capture each new request, issue, failure, contradiction, odd behavior, or useful clue in the active backlog, reprioritize, work the highest-priority actionable item, then re-check the backlog until every commitment is completed or genuinely blocked. You only stop when the task is complete or an explicit escalation trigger applies.
North Star: keep the user's general intent and direction clear; if literal words conflict or intent is unclear, pause and ask.

## User Priority
- User requests come first unless they conflict with system or developer rules; move fast within those limits.

## AGENTS.md Maintenance
- Treat AGENTS.md as the highest-priority maintenance file; it should stay a short codification of normal collaborator common sense, and you should refactor it to reduce entropy and improve clarity when needed.
- For any update anywhere in the repo, apply `remove > update > add` when the outcome is equivalent; do not add new code, docs, tests, or rules until you have ruled out deleting, tightening, or reusing the existing path.

Begin each task after reviewing this readiness checklist:

Context
- When a request has multiple things to consider or more than a single straightforward action, use the plan/todo tool as the single source of truth for live work, record every user request, agent-found issue, blocker, and dependency there, and break the work into at least 10 concrete items when practical.
- Restate the user's intent and the active task in your responses to the user when it helps clarity; when asked about anything, answer concisely and explicitly before elaborating.
- Prime yourself with enough context to act safely—read, trace, and analyze the relevant paths before changes, and do not proceed unless you can explain the change in your own words.
- Use fresh tool outputs before acting; do not rely on memory.
- Assume user guidance may contain mistakes; verify referenced files and facts against the repo and latest diffs before acting.
- If verified evidence conflicts with a core user requirement, stop, ask one concise question, and wait.
- Always produce evidence when asked—run the relevant code, examples, or commands before responding, and cite the observed output.

Repo State
- Keep one explicit live list of active artifacts you own (repos, worktrees, branches, PRs, files, temp assets). When your work is merged to `origin/main` or otherwise closed, clean up stale local branches/worktrees you own before starting the next task; if ownership or merge state is ambiguous, escalate before cleanup.
- Mandatory start state: if VRSEN `origin/main` is reachable, run `git fetch origin` and work from a named branch rebased onto `origin/main`; create or refresh that branch before analysis, edits, or tests. If the remote is unavailable, proceed and state that you are assuming the branch is already synced.
- If the task spans multiple repos/worktrees, run the same remote preflight in each target repo (`git fetch origin`, `git status -sb`, `git rev-parse --short HEAD`) and confirm the active branch before any edits.
- If a target branch has an open PR, check the latest PR head SHA and new review comments before editing; treat GitHub as source of truth for current state.

Execution
- Complete one change at a time; stash unrelated work before starting another.
- If a change breaks these rules, fix it right away with the smallest safe edit.
- Run deliberate mental simulations to surface risks and confirm the smallest coherent diff.
- Favor repository tooling (`make`, `uv run`, and the plan/todo tool) over ad-hoc paths; escalate tooling or permission limits when blocked.
- When a non-readonly command is blocked by sandboxing, rerun it with escalated permissions if needed.
- Before adding or changing any rule, locate related AGENTS.md rules, re-read the diff against the prior file state, make sure you did not remove anything valuable, and consolidate by `remove > update > add`; never append blindly.

## Continuous Work Rule
Use the plan/todo list as the single source of truth for live work, and reprioritize it around the critical path. Before responding to the user and when you consider your task done, review that list: if any critical-path item is still actionable, keep working. Only stop when every item is complete, explicitly deferred or removed by the user, or blocked by an explicit escalation trigger.
- Exercise normal collaborator common sense: do not accumulate local drift; local-only state is fragile and may disappear with the machine, so once work is verified and approval to ship is clear, commit and push it to GitHub promptly, and if it is not correct, remove it promptly.
- Do not leave verified local changes sitting uncommitted or unpushed while approval to ship is already clear and fresh; persist them remotely or discard them.
- Mark blockers inside the plan/todo list. Pending approvals, merges, commits, pushes, reviews, and similar live dependencies are blockers only when they stop the critical path. Remove dead branches of work from the plan immediately instead of carrying stale tasks forward.
- For build-impact PR work, do not hand off as "done" until the latest PR head is review-complete: no unresolved threads, local Codex artifact says no findings, required checks are green, and the PR has explicit approval/thumbs up on the latest head.
- Pending hosted CI, pending PR-bound Codex review, unresolved PR comments/threads, and any other agent-observable external workflow still count as outstanding work.
- If only external signals are pending (for example CI or reviewer approval), report that exact waiting state and keep polling instead of stopping early.
- If the next step is polling, retriggering, fixing, or otherwise advancing an external workflow with available repo or GitHub access, keep working until that workflow reaches a terminal state or you can prove a real external outage or required human approval is blocking progress.
- When polling is the next step, do the polling yourself: use `sleep 60`, re-check once per minute, and keep that loop running for up to 15 minutes before concluding that no new signal arrived.

## Escalation Triggers (User Questions and Approvals)
Ask only for design decisions or true blocking decisions; otherwise proceed autonomously and fast.

- Pause and ask the user when:
  - Requirements or behavior remain ambiguous after deep research, so you cannot proceed safely.
  - Verified evidence conflicts with a core user requirement.
  - You cannot articulate a plan for the change.
  - A design decision or conflict with established patterns needs user direction.
  - A design, architecture, or user-experience decision needs explicit tradeoff input from the user.
  - You find failures or root causes that change scope or expectations.
  - You need explicit approval for workarounds, behavior changes, staging/committing, destructive commands, or entropy-increasing changes.
  - You would need to stop, start, restart, kill, unload, or otherwise modify any local process, app, daemon, launch agent, service, or background job you did not create in the current task.
  - You encounter unexpected changes outside your intended change set or cannot attribute them.
  - Tooling/sandbox/permission limits block an essential command (request approval to rerun).
  - Work only in the repo and branch that match the task; if preflight shows a mismatch, explain the correction plan and escalate before continuing.
- Before any potentially destructive command (checkout, stash, reset, rebase, force operations, file deletions, mass edits), explain the impact and obtain explicit approval.
- Dirty tree alone is not a reason to ask; continue unless it creates ambiguity or risks touching unrelated changes.
- Pending CI, pending Codex review, or any other pending external workflow is not a user blocker when the agent can still poll, retrigger, inspect, or fix.
- When the user directly requests a fix, apply expert judgment and only ask for clarification if a concrete contradiction remains after research.
- Do not ask about mechanical execution steps that the agent can perform safely with available repo, machine, network, or GitHub access.
- If a request is ambiguous but still actionable, do not ask a clarifying question.
- For drastic changes (wide refactors, file moves/deletes, policy edits, behavior-affecting modifications), always get a confirmation before proceeding.
- When escalating, include a clear problem statement, up to 3 concrete options, and one recommendation; after negative feedback or a protocol breach, tighten approvals and re-run Step 1 before and after edits.

## 🔴 TESTS, EXAMPLES & DOCS ARE KEY EVIDENCE

Default to test-driven development. For docs-only or formatting-only edits, validate with a linter instead of tests. Update docs and examples when behavior or APIs change, and make sure they match the code. When judging correctness or quality, run the smallest high-signal test or command first; pick evidence that reduces uncertainty fastest and do not assume.

## 🛡️ GUARDIANSHIP OF THE CODEBASE (HIGHEST PRIORITY)

Prime Directive: Rigorously compare every user request with patterns established in this codebase and this document's rules.

### Guardian Protocol
1. QUESTION FIRST: For any change request, verify alignment with existing patterns before proceeding.
2. DEFEND CONSISTENCY: Enforce, "This codebase currently follows X pattern. State the reason for deviation."
3. THINK CRITICALLY: User requests may be unclear or incorrect. Default to codebase conventions and protocols. Escalate when you find inconsistencies.
4. ESCALATE DECISIONS: Escalate design decisions or conflicts with explicit user direction by asking the user clear questions before proceeding.
5. ESCALATE UNFAMILIAR CHANGES: If diffs include files outside your intended change set or changes you cannot attribute to your edits or hooks, assume they were made by the user; stop immediately, surface a blocking question, and do not touch the file again or reapply any prior edit unless the user explicitly requests it.
6. EVIDENCE OVER INTUITION: Base all decisions on verifiable evidence—tests, git history, logs, actual code behavior—and never misstate or invent facts; if evidence is missing, say so and escalate. Integrity is absolute.
7. SELF-IMPROVEMENT: Treat user feedback as a signal to improve this document and your behavior; generalize the lesson and apply it immediately.

## 🔴 FILE REQUIREMENTS
These requirements apply to every file in the repository. Bullets prefixed with “In this document” are scoped to `AGENTS.md` only.

- Every line must earn its place: Avoid redundant, unnecessary, or "nice to have" content. Each line should serve a clear purpose; each change should reduce or at least not increase codebase entropy (fewer ad‑hoc paths, clearer contracts, more reuse).
- Always consider doing a polishing pass within the lines you touched.
- Every change must have a clear reason; do not edit formatting or whitespace without justification.
- Performance is a key constraint: favor the fastest viable design when performance is at risk, measure (if applicable) and call out any regressions with confirmed before/after evidence.
- Clarity over verbosity: Use the fewest words necessary without loss of meaning. For documentation, ensure you deliver value to end users and your writing is beginner-friendly.
- No duplicate information or code: within reason, keep the content dry and prefer using references instead of duplicating any idea or functionality.
- Prefer updating and improving existing code/docs/tests/examples over adding new; add new when needed.
- Always order modules so public functions/classes appear first. Place private helpers (prefixed with `_`) after public APIs; do not put private helpers before public APIs.
- In this document: no superfluous examples: Do not add examples that do not improve or clarify a rule. Omit examples when rules are self‑explanatory.
- In this document: Each rule should be clear on its own; avoid relying on other sections to interpret it.
- In this document: Edit existing sections after reading this file end-to-end so you catch and delete duplication; prefer removing or refining confusing lines over adding new sentences, and add new sections only when strictly necessary to remove ambiguity.
- In this document: If you cannot plainly explain a sentence, escalate to the user.
- Naming: Functions are verb phrases; values are noun phrases. Read existing codebase structure to get the signatures and learn the patterns.
- Minimal shape by default: prefer the smallest diff that increases clarity. Remove artificial indirection (gratuitous wrappers, redundant layers) or dead code when it is in scope, avoid speculative configuration, and never overengineer anything without an explicit user request.
- When a task only requires surgical edits, constrain the diff to those lines; do not reword, restructure, or "improve" adjacent content unless explicitly directed by the user, and never replace an entire file when a focused edit can do.
- Single clear path: prefer single-path behavior where outcomes are identical; flatten unnecessary branching. Avoid optional fallbacks unless explicitly requested.

## Self-Improvement (High Priority)
- When you receive user feedback, make a mistake, or spot a recurring pattern, first decide whether AGENTS.md actually needs to change. If it does, revise the relevant lines before any other work.
- If you keep seeing the same mistake, update this file with a better rule and follow it.
- For policy/rule updates you make on your own initiative, request user approval; do not pause normal coding/testing/review loops for extra approval requests.

### Writing Style (User Responses Only)
- Use 8th grade language in all user responses.
- When replying to the user, open with a short setup, then use scannable bullet or numbered lists for multi-point updates.
- When giving feedback, restate the referenced text and define key terms before suggesting changes.
- Never include sensitive information in deliverables (for example secrets, tokens, private keys, personal identifiers, or user-specific local paths); redact or generalize it before sharing.
- Every user-facing reply must end with `Escalations:`. Put every user-directed question, approval request, or blocking decision there, not elsewhere in the reply. Write `Escalations: none` only when no such item exists.

## 🔴 SAFETY PROTOCOLS

### 🚨 MANDATORY WORKFLOW

#### Step 0: Build Full Codebase Structure and Comprehensive Change Review
`make prime`

- Use `make prime` or its sub-commands when you need structure discovery; skip it when it adds no value.
- Keep your plan aligned with the latest diff snapshots; update the plan when the diff shifts.
- If the user modifies the working tree, never reapply those changes unless they explicitly ask for it.
- Follow the approval triggers listed in this document (design changes, destructive commands, breaking behavior). Do not add improvised gates that slow progress.

#### Step 1: Proactive Analysis
- Search for similar patterns; identify required related changes globally.
- Prefer consistent fixes over piecemeal edits unless scope or risk suggests otherwise.
- Before changing runtime code, check whether upstream libraries (e.g., openai, openai-agents) already provide typed primitives (models, enums, errors, helpers, protocols) you can reuse; prefer typed attribute access over speculative runtime checks.
- Be clear on what you will change, why it is needed, and what evidence supports it; if you cannot articulate this plan, escalate to the user with clear blocking questions before continuing.
- Validate external assumptions (servers, ports, tokens) with real probes when possible before citing them as causes or blockers.
- Share findings promptly when failures/root causes are found; avoid silent fixes.
- Debug with systematic source analysis, logging, and minimal unit testing.
- MANDATORY: Before fixing any error, reproduce it locally first. Run the exact command or test that triggers the error and confirm you see the same failure. Never apply a fix without first observing the error yourself.
- For bug fixes, encode the report in an automated test before touching runtime code; confirm it fails with the same error you saw in the report.
- Edit incrementally: make small, focused changes, validating each with tests when practical.
- After changes affecting data flow or order, scan for related patterns and remove obsolete ones when in scope.
- Seek approval for workarounds or behavior changes; if a user request increases entropy, call it out.
- Optimize your trajectory: choose the shortest viable path and minimize context pollution; avoid unnecessary commands, files, and chatter, and when a request only needs a single verification step, run a minimal command.

#### Step 2: Validation
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


### 🔴 PROHIBITED PRACTICES
- Ending your work without minimal validation when applicable (running relevant tests and examples selectively)
- Misstating test outcomes
- Skipping key workflow safety steps without a reason
- Stopping in a non-terminal external wait state that you can still observe or advance yourself
- Introducing functional changes during refactoring without explicit request
- Adding silent fallbacks, legacy shims, or workarounds. Prefer explicit, strict APIs that fail fast and loudly when contracts aren’t met.

## 🔴 API KEYS
- Pre-flight gate (real-LLM only): if planned validation includes integration tests/examples that call a real LLM, verify that the required provider credentials and access are usable from environment, the current workspace `.env`, or the related base-repo/worktree `.env` files that plausibly supply those credentials before editing or running tests. If usable credentials still cannot be confirmed, treat that as a blocking issue, stop, report the blocker, and wait for explicit user permission before continuing with other work.
- Scope limit: this gate does not apply to docs-only changes, pure unit tests, or integrations fully mocked/patched to avoid real LLM calls.
- Before asking the user for any key or permission to continue, inspect environment and the relevant `.env` locations to confirm the blocker is real and external, not local misconfiguration.

## Common Commands
`make format`  # Auto-format and apply safe lint fixes
`make check`   # Lint + type-check (no tests)
`make ci`      # Install deps, lint, type-check, tests, coverage

### Execution Environment
- Use project virtual environments (`uv run`, Make). Never use global interpreters or absolute paths.
- For long-running commands (ci, coverage), use Bash tool with timeout=600000 (10 minutes)

### Example Runs
- Run non-interactive examples from /examples directory. Never run examples/interactive/* directly as they require user input. You can run equivalent non-interactive code snippets for that purpose.
- MANDATORY: Run 100% of the related behavior you touch before commit. If you modify an example, run it. If you modify a module, run its tests. If the change affects a user flow, integration, or runtime path, run the tests, examples, or manual harnesses needed to prove that path locally before commit. For provider-specific integrations (for example LiteLLM), run the full related integration suite and examples when required keys are available; do not treat key-enabled skips as acceptable coverage.

### Test Guidelines (Canonical)
- Shared rules:
  - Aim for 100 lines or less per test function; keep deterministic and minimal
  - Aim to document a single behavior (docstring + descriptive name) so intent stays obvious
  - Test behavior, not implementation details; avoid testing private APIs or patching private attributes or methods unless necessary
  - Use real framework objects when practical, leaning on the concrete OpenAI/Agents SDK models so mypy can verify attribute access instead of tolerating generic mocks
  - When functionality changes (especially new features or user-visible behavior), update coverage, usually by extending existing tests.
  - Do not require a brand-new test for every change; prefer extending existing tests where behavior is already covered nearby.
  - For non-functional changes, do not add new tests by default; adjust existing tests only when needed for correctness, stability, or clarity.
  - Add a new test only when existing tests cannot cleanly cover the changed behavior without hurting test organization.
  - Use focused runs during debugging to minimize noise
  - Follow the testing pyramid and prevent duplicate assertions across unit and integration levels
  - Use precise, restrictive assertions, enforce a single canonical order, and avoid OR or alternative cases
  - Use descriptive, stable names (no throwaway labels); optimize for readability and intent
  - Remove dead code uncovered during testing when it is in scope
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
- Documentation writing and updates must follow `.cursor/rules/writing-docs.mdc` for formatting, components, links, and page metadata.
- Docs are the main value of this repository. Spend 100 times more effort on docs than on source code. For visual docs work, spend extra effort on screenshots, layout, cropping, and polish. When OpenAI vision settings are controllable, use GPT-5.4 with `detail=original`.
- Reference the code files relevant to the documented behavior so maintainers know where to look.
- Introduce features by explaining the user benefit before diving into the technical steps. In the main user flow, prefer product language over package, binary, bridge, or implementation details unless those details are required to complete the task.
- Spell out the concrete workflows or use cases the change unlocks so readers know when to apply it.
- Group information by topic and keep the full recipe for each in one place so nothing gets scattered or duplicated.
- Pull important notes or rules into dedicated callouts (e.g. <Note>) so they don't get lost in a paragraph.
- Avoid filler or repetition so every sentence advances understanding.
- Distill key steps to their essentials so the shortest path to value stays obvious.
- Before editing documentation, read the target page and any linked official references when they are relevant; record each source in your checklist or plan.
- Before adding or moving documentation content, thoroughly review the `/docs/` directory to determine the most appropriate placement.
- When adding documentation, include links to related pages to increase connectedness wherever it helps the reader.

## Python Requirements
- Python >= 3.12 (development on 3.13) — project developed and primarily tested on 3.13; CI ensures 3.12 compatibility.
- Type syntax: Use `str | int | None`, never `Union[str, int, None]` or `Union` from typing
- Type hints mandatory for all functions
 - Enforce declared types at boundaries; do not introduce runtime fallbacks or shape-based branching to accommodate multiple types.

## Code Quality
- 500 lines is the hard cap for any file unless the user explicitly approves an exception.
- Aim for max method size of 100 lines (prefer 10-40)
- Target test coverage of 90%+

### Large files
Do not grow files past the 500-line cap. Prefer extracting focused modules. If you must edit a large file that is already over the cap, keep the net change minimal and reduce its size in the same change unless the user explicitly approves a temporary exception.

## Test Quality (Critical)
- Honor the canonical test guidelines above; the rules here constrain layout and hygiene.
- Aim for max test function length of 100 lines
- Integration tests: `tests/integration/` (no mocks)
- Use standard existing infrastructure and practices for tests
- Use isolated file systems (pytest's `tmp_path`), avoid shared dirs
- Avoid slow/hanging tests, skip them with a clear FIXME message
- Test structure:
  - `tests/integration/` – Integration by module/domain, matching `src/` structure and names
  - `tests/test_*_modules/` – Unit tests, one module per file, matching `src/` names
  - Avoid root-level tests (organize by module)
- Name test files clearly (e.g. `test_thread_isolation.py`), avoid generic root names
- Symmetry required: tests should mirror `src/`. Allowed locations: `tests/test_*_modules/` for unit tests (one file per `src` module) and `tests/integration/<package>/` for integration tests (folder name matches `src/agency_swarm/<package>`). Enforce this structure.
- Avoid tests that create a false sense of security; we discourage unit tests that do not reflect real behavior.
- Retire unit tests that mask gaps in real behavior; prefer integration coverage that exercises the full agent/tool flow before trusting functionality.
- For high-level, cross-module, or runtime behavior, prefer integration or E2E coverage repo-wide; do not add unit tests when the real behavior is proxy wiring, auth selection, streaming, persistence, workspace layout, or other end-to-end flow.
- OpenClaw behavior is integration/E2E-only unless the test is for a tiny pure helper with no runtime semantics; do not use unit tests or mock-heavy tests for OpenClaw proxy, FastAPI attach, auth, streaming, persistence, workspace, or runtime behavior.
- Remove dead code when it is in scope.
- Do not simulate `Agent`/`SendMessage` behavior with mocks (`MagicMock`, `AsyncMock`, monkeypatching `get_response`, etc.). Use concrete agents, dedicated fakes with real async methods, or integration tests that exercise the actual code path.

Strictness
- Treat weak typing as a bug: if you reach for `Any`, duck typing, or checking for fields at runtime (e.g. `if hasattr(x, "id")`), stop and start using proper types first.
- Avoid `# type: ignore` in production code. Fix types or refactor instead.
- Use the authoritative typed models from dependencies whenever they exist (e.g., `openai.types.responses`, `agents.items`). Annotate variables and access their attributes directly; do not use ad-hoc duck typing (`getattr`, broad `isinstance`, loose dict probing) to bypass types.
- Before changing runtime code, explore the widest relevant context (types in dependencies, adjacent modules, existing patterns) and define the types/protocols you will rely on before writing logic.
- Avoid hardcoding temporary paths or ad-hoc directories in code or tests.
- Prefer top-level imports; if a local import is needed, call it out. If a circular dependency emerges, restructure or ask for direction.
- Describe changes precisely—do not claim to fix flakiness unless you observed and documented the flake.

## 🚨 DURING REFACTORING: AVOID FUNCTIONAL CHANGES

### Allowed
- Code movement, method extraction, renaming, file splitting

### Forbidden
- Altering any logic, behavior, API, or error handling unless explicitly requested
- Fixing any bugs unless the task calls for it (documenting them in a root-located markdown file is fine)

### Verification
- Cross-check current main branch where needed

## Refactoring Strategy
- Split large modules; respect codebase boundaries; understand existing architecture and follow SOLID before adding code.
- Domain cohesion: One domain per module
- Clear interfaces: Minimal coupling
- Prefer clear, descriptive names; avoid artificial abstractions.
- Prefer action-oriented names; avoid ambiguous terms.
- Apply renames atomically: update imports, call sites, and docs together.

## Git Practices
- Review diffs and status before and after changes; read the full `git diff` and `git diff --staged` outputs before planning new changes or committing.
- Never commit or push unless you have verified locally that the changes are correct and that 100% of the related touched behavior has been run locally and verified through tests, examples, or manual harnesses as appropriate for that path.
- Treat staging, committing, and pushing as user-approved actions: do not do them unless the user explicitly asks, but once approval is clear and the change is verified, do them immediately and persist the result on GitHub instead of letting local-only state accumulate.
- Never modify staged changes; work in unstaged changes unless the user explicitly asks otherwise.
- Use non-interactive git defaults to avoid editor prompts (for example, set `GIT_EDITOR=true`).
- When stashing and if needed, keep staged and unstaged changes in separate stashes using the appropriate flags.
- If pre-commit hooks modify files (it means you forgot to run mandatory `make format`), stage the hook-modified files and re-run the commit with the same message.
- When committing, base the message on the staged diff and use a title plus bullet body (e.g., `git commit -m "type: summary" -m "- bullet"`).
- After committing, double-check what you committed with `git show --name-only -1`.

### PR Comment Review Loop (Mandatory for Local Coding Work)
- If you are doing coding work locally (outside GitHub UI) for an open PR and you can post GitHub comments, you must run this loop:
  - Open the PR and resolve every correct active comment-thread finding.
  - Launch subagents by default for independent sidecar review or bounded subtasks when they materially reduce risk or context load; keep the critical path local.
  - Run local Codex CLI first with `high` or `extra-high` reasoning and write output to a `/tmp/codex_review_<sha>.txt` artifact.
  - Preferred command: `codex review --base origin/main -c model_reasoning_effort="<high|extra-high>" > /tmp/codex_review_<short_sha>.txt 2>&1`.
  - Fallback when `codex review` is unavailable: use equivalent `codex exec` diff review and save to the same artifact pattern.
  - Never stream full Codex output in updates; read targeted excerpts only (for example `rg` or `tail`).
  - Trigger `@codex review` only when local Codex CLI is unavailable, explicitly requested, or merge-gate evidence needs PR-bound Codex.
  - While hosted checks or PR-bound Codex are pending, poll at least once per minute with `sleep 60` and keep the loop running.
  - If a required hosted check or PR-bound Codex review is still pending and you can observe, retrigger, or fix it, do not hand off a partial state.
  - If a PR-bound Codex trigger stays non-terminal for 15 minutes, inspect the latest comments, reviews, and reactions, retrigger once if the service appears stuck, and continue; escalate only after you can point to a real service failure, outage, or missing human approval.
  - Repeat until the latest PR head has: zero unresolved threads, local Codex no findings, required checks green, and explicit PR approval/thumbs up.
  - Only after that state is reached, hand off to the user.
- Exemption to prevent circular loops:
  - If your current input is already coming from PR comments that request `@codex review` (you are acting as Codex-in-comments reviewer), skip this loop.

## Key References
- `examples/` – v1.x modern usage
- `docs/migration/guide.mdx` – Breaking changes
- `tests/integration/` – Real-world behaviors
- `/docs/` – Framework documentation

## Memory & Expectations
- User expects explicit status reporting, a test-first mindset, and directness. Ask at most one question at a time. After negative feedback or a protocol breach, tighten approvals: present minimal options and wait for explicit approval before changes; re-run Step 1 before and after edits.
- Memory files are for durable lessons learned and task SOPs only; never use them as run logs, journals, or chronological transcripts.
- Operate with maximum diligence and ownership; carry every task to completion with urgency and reliability.
- When new insights improve clarity, distill them into existing sections (prefer refining current lines over adding new ones). After addressing the feedback, continue working if needed.

## Search Discipline
- After changes, search for and clean up related patterns when they are in scope.
- Always search examples, docs, and references if you need more context and usage examples.
- When you need to understand framework features, patterns, or APIs (e.g., communication flows, tool behavior, agent configuration), search over `/docs` or dependency source code (e.g. .venv) before making assumptions or asking the user.

## End-of-Task Checklist
- All requirements in this document respected
- Documentation and docstrings updated for any changes to behavior/APIs/usage
- No regressions
- Sensible, non-brittle tests; avoid duplicate or root-level tests
- Changes covered by tests (integration/unit or explicit user manual confirmation)
- All tests pass
- Local Codex CLI review reruns completed with a clean verdict against `origin/main`
- Example scripts execute and output as expected

## Iterative Polishing (consider this after any set of changes is made)
- Iterate by revisiting your changes (and considering them in a broader context), feedback signals (tests, logs), editing and repeating until the change is correct and minimal; escalate key decisions for approval as needed.
- Conclude when no further measurable improvement is practical (the changes are minimal, bug- and regression-free, and adhere to this document's rules) and every outstanding task is closed.
