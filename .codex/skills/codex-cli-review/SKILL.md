---
name: codex-cli-review
description: Use when a local Codex CLI review, pull-request opening or update compliance check, pull-request comment review loop, or saved Codex review artifact is required for this repo.
---

# Codex CLI Review

Use this skill for local Codex review artifacts and pull-request review loops.

## Governance Primer

- Before opening, updating, merging, or release-reviewing a pull request, read `AGENTS.md`, `CONTRIBUTING.md`, `.github/PULL_REQUEST_TEMPLATE/pull_request_template.md`, and the relevant `.github/workflows/*` for template, test, release, or publish rules.
- Verify PR title, summary, test plan, issue number, checked checklist, no unrelated changes, unresolved threads, and required checks before handoff.
- The pull-request body must satisfy the live template and workflow requirements when opened, and must stay compliant after edits or synchronize events.
- Any live workflow label or comment that blocks the pull request is a critical-path blocker until fixed, removed by the workflow, or explicitly excepted with checked policy evidence.

## Human Review And QA Packet

- Prepare this packet before a manager requests merge approval.
- Group the changes for quick GitHub review and explain why each group exists.
- Ask the user to leave comments or questions on GitHub and request one alignment confirmation.
- For bug-fix, feature, and any other pull request with user-testable behavior, provide one concrete QA target, for example a locally installed build, exact testable artifact, preview environment; name the changed user flow it exercises.
- For non-runtime pull requests, such as docs-only and policy-only changes, state that product QA is not applicable because no user-testable behavior changed; still request alignment confirmation.
- For user-testable behavior, provide clear QA steps that exercise the changed behavior and name any remaining blocker or gap.

## Base Selection

- Use the base explicitly requested by the user or policy.
- Use `origin/main` unless the user or live pull request names another base.
- Use the exact release base for release-gate review.

## Canonical Review

```bash
codex -m gpt-5.5 review --base <base> -c model_reasoning_effort="xhigh" > /tmp/codex_review_$(git rev-parse --short HEAD).txt 2>&1
```

If GPT-5.5 is unavailable, use the strongest available GPT-5.x review path, record the exact model, and do not rely on unknown defaults.

## Fallback

If `codex review` is unavailable or stuck, use a narrow `codex exec` review prompt and save output to `/tmp/codex_review_<short_sha>.txt`.

Prompt shape:

```text
Review the current diff against <base> for real correctness, regression, security, data-boundary, policy, repo-rule, PR compliance, review-gate, test/QA evidence, excessive-scope, and unintentional-drift issues. Treat real issues as P0/P1/P2 findings by risk, including missing required gates or evidence. Ignore style nits. Return exactly "No findings." if clean.
```

## Finding Severity

- `P0`: public release harm, data loss, security or privacy exposure, destructive behavior, or core Agency Swarm runtime release-path breakage.
- `P1`: real bug or regression risk, unapproved user-visible behavior change, missing or invalid merge/release gate likely to ship bad state, or architecture drift likely to break behavior or future maintenance.
- `P2`: excessive or unjustified drift, unrelated code/docs/test churn, PR compliance failure, missing required evidence, or stale or mismatched review artifact.

## Pull-Request Review Loop

1. Read the pull request, latest head SHA, active review comments, unresolved threads, and required checks.
2. Resolve every correct active thread or official review finding locally, or record the manager's checked-evidence downgrade or override.
3. Pull-request-specific work includes comment review, thread replies, issue-link checks, pull-request body edits, and other GitHub-side mutations.
4. Keep pull-request-specific work on the local critical path when a bounded Codex pass covers it; use a subagent only when broader orchestration is needed.
5. Trigger `@codex review` only when local Codex review and suitable subagents are unavailable, when the user asked for it, or when merge-gate proof needs pull-request-bound Codex.
6. If the current input already came from pull-request comments that asked for `@codex review`, skip nested review loops and resolve the scoped comments directly.
7. Poll hosted checks or pull-request Codex at least once a minute while they are pending.
8. If local Codex or pull-request Codex stays non-terminal for 15 minutes, inspect state and retrigger once if it looks stuck. If required GitHub checks stay non-terminal for 30 minutes, inspect logs and continue or escalate with proof of a real service blocker.
9. Do not hand off build-impact pull-request work until the latest head has zero unresolved threads, a clean local Codex review artifact, and green required checks. Stale, interrupted, wrong-base, wrong-head, or pre-final review artifacts do not satisfy this gate; any later commit or merge invalidates it. Then use the human review gate in `AGENTS.md`.

## Output

Report whether the result was `No findings.`, any concrete findings with file paths, and whether a fallback or narrowed scope was used.
