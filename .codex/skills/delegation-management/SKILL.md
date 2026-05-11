---
name: delegation-management
description: Use when a manager delegates to subagents, scopes staged worker tasks, decides whether to reuse or rotate workers, or reviews delegated output before relying on it.
---

# Delegation Management

Use this skill when delegation affects correctness, queue control, review quality, or context management.

## Manager Duties

- Stay at manager height: own the queue, mandate, critical path, final review, merge/release decisions, and destructive-action decisions.
- Managers may inspect, review, run tests, integrate worker output, and perform mechanical git operations. When active policy requires worker writes, managers must not author those edits unless the user explicitly assigns them a worker scope.
- Worker output is evidence, not final truth. Verify it before relying on it or presenting it as final.
- When reviewing delegated output, load and follow the same relevant skill or skills the worker was told to use, and verify whether the worker actually used them.
- Treat subagents as focused independent contributors or counsel inside their mandate, not narrow command executors.

## Delegation Shape

1. Delegate only when it protects the manager context window, shortens the critical path, improves plan quality, or enables parallel investigation.
2. Start each task with the exact user ask, repo, branch, relevant artifacts, source pointers, inspected evidence, unknowns to acquire, success condition, output format, and hard limits.
3. Do not widen worker prompts beyond exact user words, standing policy, and checked evidence. Similar wording or adjacent concepts are not authority.
4. Put inferred assumptions on a separate `Inferred assumptions` line. Mark them as unapproved, and ask or escalate instead of letting the worker implement them when they affect scope, behavior, wording, or permission.
5. If the prompt carries context from another conversation, name that source explicitly; write "the end user told the manager" or "the manager's previous response", not bare "the user" or "previous response" when the worker cannot see that speaker.
6. For large work, use staged delegation when useful: analysis or discussion first, implementation second, review or polish third.
7. Let workers ask questions, request scope extensions, return blockers, and surface tradeoffs. Do not force immediate delivery when missing facts could change the result.
8. Keep local environment repair, credentials, and machine-specific setup on the manager thread unless the user delegates that work explicitly.
9. Use built-in subagents for delegated work. External CLI agents, review commands, and ad hoc agent processes are tools or review evidence, not delegation, unless the user explicitly names them and grants that scope.
10. Keep pull-request-specific work off the manager thread when possible. Prefer `.codex/skills/codex-cli-review` when a bounded local Codex pass cleanly covers the task; use one fitting built-in subagent otherwise, and surface a blocker only if no allowed path works.
11. After delegation starts, do not interrupt, rush, or repeatedly ping workers unless the user changes scope or you have clear proof of failure.

## Planning Worker Tradeoff

- Use a planning or discussion worker only when expected value beats priming and context-loading cost.
- Treat model capability, reasoning effort, and clean context as reliability signals when choosing or reviewing workers.
- Use the same primed worker for discussion and implementation when continuity improves quality.
- Rotate to a fresh worker when context is overloaded, contaminated, stale, mistake-prone, or when independent review matters more than continuity; by default, weigh that worker as more reliable than the contaminated manager thread while still checking its output as evidence.

## Boundaries

- Subagents treat the manager as the user proxy inside the delegated mandate.
- Workers may create branches, commits, and pull requests only inside their mandate.
- Workers must not merge, publish releases, tag, force-push, delete shared artifacts, or run destructive operations unless the manager delegates that exact action for that exact artifact after review.
- Managers own shells, tmux sessions, Codex resume sessions, and polling loops spawned by them or delegated workers; reclaim or close them at task boundaries.
