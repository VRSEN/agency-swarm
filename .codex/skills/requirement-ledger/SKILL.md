---
name: requirement-ledger
description: Use when a task needs a durable active requirement queue and archive workflow. Captures only real user requests or requirements with proofread, sanitized requirement text, source pointers, category, intent, status, next action, and linked artifacts; avoids noisy transcript dumps without erasing user intent.
---

# Requirement Ledger

Use this skill when task state must survive beyond the current chat or when a request has several requirements that can drift. The ledger records work state; durable operating rules live in `AGENTS.md` or the relevant repo skill.

## Workflow

1. Record only real user requests, explicit requirements, blockers, or decisions that change the work.
2. Store a proofread, privacy-preserving requirement restatement in `original`; do not copy exact private wording, profanity, speech errors, or raw transcript phrasing. Preserve meaning, source pointers, context, and auditability.
3. Add a source pointer for each item, such as `chat:2026-04-15 user#2`, `PR#123 comment 456`, or `docs/foo.md:42`.
4. Plan the strategy for tackling the active queue before editing it, then reread the full active ledger and reprioritize deliberately at each task boundary.
5. Keep active unfulfilled work in strategic chronological order; do not randomize, convenience-sort, or group items away from their original sequence.
6. Before presenting a revised ledger, list every active unfulfilled requirement with sanitized `original` and source pointers.
7. When an item is done, run `complete` so it moves out of the active queue and into the archive.
8. If a ledger revision is rejected, run `reject`; failed revision output is not source of truth and must be rebuilt from original sources.
9. Consider the ledger on every user message; update it only when the message creates or changes a real request, requirement, decision, blocker, artifact, status, or critical-path fact.
10. Update the ledger at task switches, meaningful progress points, artifact state changes, before commits, before pull-request or release actions, and before a substantive reply or stop when one of those events changes real ledger state.
11. Register every active artifact you touch as a ledger-linked item or note: repos, worktrees, branches, PRs, conflicted states, temp artifacts, and generated review artifacts that still matter.
12. Treat every unshipped or undiscarded artifact as a blocker; do not let it fall out of the active queue until it is shipped, explicitly discarded, or archived with resolution.
13. Before opening a new PR for ongoing work, record the existing related PR and why it cannot be reused; if that reason is missing, reuse the existing PR instead.
14. Before creating a public issue, pull request, docs page, or release note from ledger work, search the active ledger, archive, open and closed issues, related pull requests, and recent history; reuse or update existing artifacts when they cover the work.
15. Track GitHub issue links on the relevant ledger item. Public bug issues should preserve useful repro details, evidence, expected behavior, and related links unless the details are sensitive.

## CLI

Run the bundled script from the repository root:

```bash
python .codex/skills/requirement-ledger/scripts/requirement_ledger.py --help
```

Default files:

- Active queue: `.codex/requirements-ledger/active.json`
- Archive: `.codex/requirements-ledger/archive.jsonl`

Use `--ledger-dir <path>` for a temporary or task-specific ledger.

New active ledger items must carry an `artifacts` list, even when it is empty. Use it for the live handles that already cover the work, such as `PR#123`, `branch:origin/main`, `tag:v1.2.3`, `release:v1.2.3`, or `gist:abc123`, so the next agent finds existing work before creating anything new.

Legacy archive entries that predate `artifacts` stay readable; the tool treats missing archive artifacts as `[]` on read. Do not hand-edit archive data just to add the field.

Legacy Agency active ledgers using `codex-requirement-ledger/v2` are migrated on read to the current schema and backfilled with `artifacts: []` when needed. Current-schema active entries still require an explicit `artifacts` list.

## Commands

Add an item:

```bash
python .codex/skills/requirement-ledger/scripts/requirement_ledger.py add \
  --category tooling \
  --title "Build reusable requirement ledger skill" \
  --original "build a durable active requirement queue and archive workflow" \
  --intent "Future agents need a compact active queue and archive workflow." \
  --next-action "Create the skill files and run a CLI smoke test." \
  --source-pointer "chat:2026-04-15 user#2" \
  --artifact "branch:origin/main"
```

For long reviewed requirement text, read `original` from a file instead of the shell:

```bash
python .codex/skills/requirement-ledger/scripts/requirement_ledger.py add \
  --category tooling \
  --title "Ingest reviewed user requests" \
  --original-file /tmp/sanitized_request.txt \
  --intent "Keep proofread requirement text in the ledger without shell-length limits." \
  --next-action "Reconcile the transcript entry against the active ledger." \
  --source-pointer "chat:2026-04-22 user#1"
```

Append linked artifacts on an existing item:

```bash
python .codex/skills/requirement-ledger/scripts/requirement_ledger.py update REQ-20260415-001 \
  --artifact "PR#123"
```

Update active state:

```bash
python .codex/skills/requirement-ledger/scripts/requirement_ledger.py update REQ-20260415-001 \
  --status in_progress \
  --next-action "Run the focused smoke test."
```

Move finished work to the archive:

```bash
python .codex/skills/requirement-ledger/scripts/requirement_ledger.py complete REQ-20260415-001 \
  --resolution "Skill and CLI smoke test completed."
```

Mark rejected ledger revision as failed:

```bash
python .codex/skills/requirement-ledger/scripts/requirement_ledger.py reject REQ-20260415-001 \
  --resolution "Ledger revision was rejected and must be rebuilt from original sources."
```

List current state:

```bash
python .codex/skills/requirement-ledger/scripts/requirement_ledger.py list --archive
```

## Rules

- Do not add raw user-message dumps, images, logs, stack traces, exact private wording, profanity, speech errors, or other private data to durable ledger text. If exact source text matters, keep it outside the ledger and point to it with a source pointer.
- Noise reduction may remove non-requirement chatter and duplicates, but it must not delete, flatten, or overcompress the user's actual request.
- Keep the tooling simple: validate required fields, but avoid arbitrary caps or normalization that distorts meaning.
- Never rewrite the whole queue file. Use item-level `add`, `update`, `complete`, or `reject` operations so source pointers, sanitized requirement text, and order survive.
- Avoid vague one-off labels such as "cleanup"; name the exact requirement set, source range, and intended ledger change.
- Prefer one item per requirement; do not mix status notes, design choices, and implementation steps in one item.
- Use `blocked` only when the next action truly needs a user decision or missing external input.
- Use `complete` or `reject` instead of setting active items to a terminal status; the archive is the terminal-work record.
- Keep artifact state current at task boundaries so the ledger always reflects the real critical path, not a stale memory of it.
- Clean up stale owned branches and worktrees only after ownership and merge state are clear.
- Do not use the ledger as policy storage. If work exposes a durable process gap, update `AGENTS.md` or the relevant repo skill; use the ledger only for state tracking: active requests, decisions, blockers, evidence, artifacts, and source links.
- Own ledger mechanics inside the agent workflow. Do not ask the user to decide script fields, command shapes, or internal storage unless they change user-visible behavior, public artifacts, destructive actions, visibility boundaries, or another `AGENTS.md` escalation trigger.
