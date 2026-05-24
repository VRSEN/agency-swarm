---
name: delegation-management
description: Use when a manager delegates to subagents, scopes staged worker tasks, decides whether to reuse or rotate workers, or reviews delegated output before relying on it.
---

# Delegation Management

Use this skill when delegation affects correctness, queue control, review quality, or context management.

## Manager Duties

- Stay at manager height: own the queue, mandate, critical path, final review, merge/release decisions, and destructive-action decisions.
- Managers may inspect, review, run tests, integrate worker output, and perform mechanical git operations. For this repo, they must not author non-trivial code or test edits unless the user explicitly approves.
- Worker output is evidence, not final truth. Verify it before relying on it or presenting it as final.
- When reviewing delegated output, load and follow the same relevant skill or skills the worker was told to use, and verify whether the worker actually used them.
- Treat subagents as focused independent contributors or counsel inside their mandate, not narrow command executors.

## Delegation Shape

1. Delegate only when it protects the manager context window, shortens the critical path, improves plan quality, or enables parallel investigation.
2. Start each task with the exact user ask, repo, branch, relevant artifacts, source pointers, inspected evidence, unknowns to acquire, success condition, output format, and hard limits.
3. If the prompt carries context from another conversation, name that source explicitly; write "the end user told the manager" or "the manager's previous response", not bare "the user" or "previous response" when the worker cannot see that speaker.
4. For large work, use staged delegation when useful: analysis or discussion first, implementation second, review or polish third.
5. Let workers ask questions, request scope extensions, return blockers, and surface tradeoffs. Do not force immediate delivery when missing facts could change the result.
6. Keep local environment repair, credentials, and machine-specific setup on the manager thread unless the user delegates that work explicitly.
7. Choose local review, delegated worker, and assistant model paths through `AGENTS.md` Tool And Model Policy before you delegate.
8. Keep pull-request-specific work off the manager thread when possible. Prefer `.codex/skills/codex-cli-review` when a bounded local Codex pass cleanly covers the task; use one fitting worker otherwise, and surface a blocker only if neither path works.
9. After delegation starts, do not interrupt, rush, or repeatedly ping workers unless the user changes scope or you have clear proof of failure.

## Planning Worker Tradeoff

- Use a planning or discussion worker only when expected value beats priming and context-loading cost.
- Use the same primed worker for discussion and implementation when continuity improves quality.
- Rotate to a fresh worker when context is overloaded, contaminated, stale, mistake-prone, or when independent review matters more than continuity.

## Boundaries

- Subagents treat the manager as the user proxy inside the delegated mandate.
- Workers may create branches, commits, and pull requests only inside their mandate.
- Workers must not merge, publish releases, tag, force-push, delete shared artifacts, or run destructive operations unless the manager delegates that exact action for that exact artifact after review.
- Managers own shells, tmux sessions, Codex resume sessions, and polling loops spawned by them or delegated workers; reclaim or close them at task boundaries.
