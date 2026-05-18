/Users/nick/.codex/AGENTS.md

# Agency Swarm Repo Supplement

This file is a local supplement. The global policy above is primary.

## 1. Precedence And Scope

1.1 Follow the global policy first.

1.2 Repo rules may only add Agency Swarm-specific constraints.

1.3 Repo rules must not weaken global user-word, mandate, evidence, privacy, public-mutation, escalation, ledger, delegation, or review gates.

1.4 If this file conflicts with the global policy, follow the global policy and surface the conflict.

1.5 Keep this file concise. Put step-by-step procedures in skills, not in this supplement.

## 2. Mandate And Public Operations

2.1 Work only inside the user-approved repo, branch, files, and visibility boundary.

2.2 Do not merge, release, tag, publish, yank, unpublish, delete branches, force push, or make public state changes without exact current user approval for that action.

2.3 Treat commits, pushes, pull requests, review submissions, hosted comments, and issue edits as separate actions that need mandate coverage.

2.4 Keep policy changes out of feature pull requests.

2.5 Reuse or repair an existing policy branch or artifact when it already covers the same policy intent.

## 3. Escalations

3.1 Escalate only when the global policy requires a user decision or the critical path is blocked.

3.2 Any user-facing blocker or user-decision response must include this exact section header and labels:

**Escalations**
Problem: State the concrete blocker, checked evidence, and real risk.
Options:
(1) State one viable path and its tradeoff.
(2) State one viable path and its tradeoff.
(3) State one viable path and its tradeoff.
Recommendation: Pick one option and give the reason.

3.3 Use only the options needed, up to three.

3.4 Ask at most one question in the escalation.

3.5 Do not include `**Escalations**` when no blocker or user decision remains.

3.6 When the user asks about completion or deletion and no escalation remains, include `Escalations: none` in the status or final update.

## 4. Runtime And Tooling

4.1 Support Python 3.12 and newer.

4.2 Center development on Python 3.13 while preserving Python 3.12 compatibility.

4.3 Use `uv` and the repo task runner instead of global Python tools.

4.4 Run `make format` after code or docs changes unless the task is read-only.

4.5 Run `make check` before staging, committing, pushing, or asking for review.

4.6 Run `make ci` before a pull request, merge-readiness claim, release-readiness claim, or repository-wide health claim.

4.7 Use the smallest focused test that proves a runtime change before broad checks.

## 5. Code And Tests

5.1 Keep changes small, typed, and aligned with existing Agency Swarm patterns.

5.2 Use type hints for all new or changed functions.

5.3 Prefer explicit contracts over silent fallbacks, compatibility shims, duck typing, or runtime shape checks.

5.4 Keep tests deterministic, offline when practical, and behavior-focused.

5.5 Put unit tests under `tests/test_*_modules/` and integration tests under `tests/integration/`, mirroring the source layout.

5.6 OpenClaw behavior requires integration or end-to-end coverage unless the code is a tiny pure helper.

5.7 Core Agent Messaging, including `Agent`, `SendMessage`, handoff, and message routing, must not be proven with generic mocks or fabricated response simulation.

## 6. Documentation

6.1 Follow `.cursor/rules/writing-docs.mdc` for documentation edits.

6.2 Introduce features through user benefit before implementation details.

6.3 Keep docs concise, grouped by topic, and linked to related pages when useful.

## 7. Skills, Ledger, And Delegation

7.1 Use scoped subagents for non-trivial edits, verification, and review when delegation is available.

7.2 Use `requirement-ledger`, `delegation-management`, `escalation-manager`, `policy-maintenance`, `test-workflow`, `codex-cli-review`, and `claude-cli-review` only as routed by the global policy and the active mandate.

7.3 Store durable ledger state under `/Users/nick/.codex`, not in the repo.

7.4 Do not hand-edit ledger files.

## 8. Mirror Link

8.1 `CLAUDE.md` must remain a symlink to `AGENTS.md`.

8.2 Before relying on or shipping a policy edit, verify `CLAUDE.md` with `ls -l CLAUDE.md` and `readlink CLAUDE.md`.

8.3 If the symlink is broken, repair only the symlink unless the user expands the mandate.
