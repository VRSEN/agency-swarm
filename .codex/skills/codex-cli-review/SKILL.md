---
name: codex-cli-review
description: Use when a local Codex CLI review, pull-request opening or update compliance check, pull-request comment review loop, or saved Codex review artifact is required.
---

# Codex CLI Review

Use this skill for local Codex review artifacts and pull-request review loops. Repo-specific `AGENTS.md` rules override the global defaults.

## Governance Primer

- Before opening, updating, merging, or release-reviewing a pull request, read the repo `AGENTS.md`, contribution rules, pull-request template, and relevant workflows for PR standards, compliance, typecheck, test, release, or publish.
- Read repo-specific source files when repo policy names them for fork behavior, release QA, user flows, or other gated work.
- Verify PR title, issue-link status or allowed exception, template sections, non-empty verification, checklist state, labels, unresolved threads, required checks, compliance comments, and no unrelated changes before handoff.
- Review the diff against exact user words, the active mandate, and checked evidence. Flag invented requirement expansion, adjacent-term rewrites, or mandate mismatch unless direct evidence or a resolved escalation supports the change.
- The pull-request body must satisfy the live template, issue-link policy, and compliance workflow when opened, and must stay compliant after edits or synchronize events.
- Treat PR-standard labels, compliance comments, unresolved review threads, required checks, and bot comment markers such as `pr-standards` or `issue-compliance` as blockers until fixed, removed by the workflow, or explicitly excepted by checked policy.

## Human Review And QA Packet

- Prepare this packet before a manager requests merge approval.
- Group changes for quick GitHub review and explain why each group exists.
- Ask the user for one alignment confirmation and direct them to leave comments or questions on GitHub when a pull request exists.
- For user-testable behavior, provide one concrete QA target and the changed flow it exercises.
- For docs-only, policy-only, or other non-runtime changes, state that product QA is not applicable because no user-testable behavior changed.

## Base Selection

- Use the base explicitly requested by the user or repo policy.
- Use any upstream-alignment, fork-delta, release-gate, or publish-state base named by the repo policy.
- Otherwise use the repo default branch, usually `origin/main`.

## Canonical Review

```bash
codex review --base <base> -m gpt-5.5 -c model_reasoning_effort="medium" > /tmp/codex_review_$(git rev-parse --short HEAD).txt 2>&1
```

If GPT-5.5 is unavailable, use the strongest available GPT-5.x review path, record the exact model, and do not rely on unknown defaults.

## Fallback

If `codex review` is unavailable or stuck, do not substitute a general-purpose CLI agent. Use a suitable built-in subagent only when the active mandate accepts independent review evidence; otherwise report the review as blocked. Save any allowed fallback output to `/tmp/codex_review_<short_sha>.txt`.

Prompt shape for an allowed built-in review fallback:

```text
Review the current diff against <base> for real correctness, regression, security, data-boundary, policy, repo-rule, PR compliance, review-gate, test/QA evidence, repo-minimality, invented requirement expansion, mandate mismatch, excessive-scope, and unintentional-divergence issues. Treat real issues as P0/P1/P2 findings by risk, including missing required gates or evidence. Ignore style nits. Return exactly "No findings." if clean.
```

## Finding Severity

- `P0`: public release harm, data loss, security or privacy exposure, destructive behavior, or release-path breakage.
- `P1`: real bug or regression risk, unapproved user-visible behavior change, missing or invalid merge/release gate likely to ship bad state, or upstream-alignment breakage likely to affect behavior or future merges.
- `P2`: excessive or unjustified drift, unrelated churn, PR compliance failure, missing required evidence, stale or mismatched review artifact, or unapproved repo divergence that increases maintenance or review risk.

## Pull-Request Review Loop

1. Read the pull request, latest head SHA, active review comments, unresolved threads, and required checks.
2. Resolve every correct active thread or official review finding locally, or record the manager's checked-evidence downgrade or override.
3. Treat pull-request-specific work as including comment review, thread replies, issue-link checks, pull-request body edits, labels, bot compliance comments, and other GitHub-side mutations.
4. Keep pull-request-specific work on the local critical path when a bounded Codex pass covers it; use a subagent only when broader orchestration is needed.
5. Trigger hosted `@codex review` only when local Codex review and suitable subagents are unavailable, when the user asked for it, or when merge-gate proof needs pull-request-bound Codex.
6. If the current input already came from hosted pull-request comments that asked for Codex review, skip nested review loops and resolve the scoped comments directly.
7. Poll hosted checks or pull-request Codex at least once a minute while they are pending.
8. If local Codex or pull-request Codex stays non-terminal for 15 minutes, inspect state and retrigger once if it looks stuck. If required checks stay non-terminal for 30 minutes, inspect logs and continue or escalate with proof of a real service blocker.
9. Do not hand off build-impact pull-request work until the latest head has zero unresolved threads, a clean local Codex review artifact, green required checks, and explicit approval or thumbs up on the latest head. Stale, interrupted, wrong-base, wrong-head, or pre-final review artifacts do not satisfy this gate; any later commit or merge invalidates it. Include the human review and QA packet before requesting merge approval.

## Output

Report whether the result was `No findings.`, any concrete findings with file paths, and whether a fallback or narrowed scope was used.
