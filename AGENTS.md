# Agency Swarm Agent Rules

This file is the public repo index for agent work in Agency Swarm. It adds repo-specific rules and skill routing only. Higher-priority system, developer, tool, and user instructions still apply.

`CLAUDE.md` must stay a symlink to `AGENTS.md`.

## Repo Scope

- Default branch: `origin/main`.
- This is a Python Agency Swarm repo.
- Keep this file focused on repo-specific rules, branch rules, and skill routing.
- Put command lists, proof steps, and long playbooks in repo skills under `.codex/skills/**`.
- Do not copy machine-wide operating rules into this file.
- Do not reference non-public files, ledgers, rules, or repos in public repo rules or docs.
- Do not add CLI, TUI, OpenCode, Bun, npm, or package-layout rules unless they have a real Python or Agency Swarm equivalent.

## Skill Routing

- Use `.codex/skills/requirement-ledger` for the active work queue, artifact tracking, blockers, and source links.
- Use `.codex/skills/policy-maintenance` for edits to `AGENTS.md`, `CLAUDE.md`, or `.codex/skills/**`.
- Use `.codex/skills/codex-cli-review` for pull-request mutation, review-thread work, merge-readiness checks, release checks, and policy review gates.
- Use `.codex/skills/test-workflow` for test choice, test writing, examples, docs checks, manual QA, live-service proof, installed-package proof, and release proof.
- Use `.codex/skills/delegation-management` when native subagents are used for scoped repo work.
- Use `.codex/skills/claude-cli-review` only as supporting review evidence when the active rules allow it.

## Mandate And Branch Rules

- Before repo edits, fetch `origin/main`, check status, and confirm the current branch and diff match the target task.
- Rebase the working branch onto fetched `origin/main` before edits when it is safe.
- If rebase would touch unrelated work, rewrite shared history, or create conflicts, use a fresh owned worktree or ask before editing.
- If the working tree has unrelated changes, leave them alone.
- If related unknown changes block safe work, ask one concrete question before editing them.
- Policy-only changes stay separate from runtime or feature changes.

## Code Rules

- Supported Python starts at 3.12.
- Development centers on Python 3.13 while keeping 3.12 compatibility.
- Type hints are required for functions.
- Use pipe-union syntax, such as `str | None`.
- Enforce declared types at boundaries.
- Do not add runtime fallbacks or shape-based branching to accept multiple types.
- Do not add silent fallbacks, legacy shims, or quiet workarounds unless the user asks.
- Learn signatures and patterns from nearby code before adding new ones.
- Prefer updating existing modules, docs, tests, and examples over adding new files.
- Put public modules, functions, and classes before private helpers.
- Use verb phrases for functions and noun phrases for values.
- Keep behavior unchanged during refactors unless the user asks for behavior change.
- Do not hide bug fixes inside refactors.
- Apply renames across imports, call sites, tests, and docs in the same change.

## Size And Structure

- No file should exceed 500 lines without explicit user approval.
- Prefer methods between 10 and 40 lines.
- Keep methods under 100 lines unless there is a strong repo-local reason.
- If an oversized file must be edited, keep the net change minimal and reduce size when that is in scope.
- Keep each changed line tied to the user mandate or checked evidence.

## Tests, Docs, And Proof

- Follow `.codex/skills/test-workflow` before claiming any code, docs, example, package, live-service, or release work is done.
- Changes to `Agent`, `SendMessage`, `OpenClaw`, streaming, examples, package behavior, or release behavior need proof that exercises the changed path.
- Unit tests live under `tests/test_*_modules/`.
- Integration tests live under `tests/integration/`.
- Mirror source layout in tests when practical.
- Target test coverage is 90 percent or higher.
- Documentation work follows `.cursor/rules/writing-docs.mdc`.
- Do not mention fork origins in user-facing docs unless the user asks.

## Pull Requests And Releases

- Before opening, updating, or relying on a pull request, use `.codex/skills/codex-cli-review`.
- A pull request with no official review record is unreviewed.
- Local review, worker review, CI, or a clean diff can support review, but does not replace required official review.
- Do not merge without explicit user approval for the exact merge.
- Before any release or release-safety claim, use `.codex/skills/test-workflow` and `.codex/skills/codex-cli-review`.
- Release cuts must be minimal and must not bundle policy or tooling churn with user-facing bug fixes.
- Do not hand off build-impact pull-request work until unresolved threads are closed and the latest head has explicit approval.
