---
name: requirement-ledger
description: Use when a task needs a durable active requirement queue and archive workflow. Captures only real user requests or requirements with close original wording, source pointers, category, intent, status, and next action; avoids noisy transcript dumps without erasing user intent.
---

# Requirement Ledger

Use this skill when task state must survive beyond the current chat or when a request has several requirements that can drift.

## Workflow

1. Record only real user requests, explicit requirements, blockers, or decisions that change the work.
2. Preserve user wording close to the original in `original`; summarize only in `intent` after the auditable wording is captured.
3. Add a source pointer for each item, such as `chat:2026-04-15 user#2`, `PR#123 comment 456`, or `docs/foo.md:42`.
4. Plan the strategy for tackling the active queue before editing it, then reprioritize deliberately.
5. Keep active unfulfilled work in strategic chronological order; do not randomize, convenience-sort, or group items away from their original sequence.
6. Before presenting a revised ledger, list every active unfulfilled requirement with `original` and source pointers.
7. When an item is done, run `complete` so it moves out of the active queue and into the archive.
8. If a ledger revision is rejected, run `reject`; failed revision output is not source of truth and must be rebuilt from original sources.

## CLI

Run the bundled script from the repository root:

```bash
python .codex/skills/requirement-ledger/scripts/requirement_ledger.py --help
```

Default files:

- Active queue: `.codex/requirements-ledger/active.json`
- Archive: `.codex/requirements-ledger/archive.jsonl`

Use `--ledger-dir <path>` for a temporary or task-specific ledger.

## Commands

Add an item:

```bash
python .codex/skills/requirement-ledger/scripts/requirement_ledger.py add \
  --category tooling \
  --title "Build reusable requirement ledger skill" \
  --original "build a durable active requirement queue and archive workflow" \
  --intent "Future agents need a compact active queue and archive workflow." \
  --next-action "Create the skill files and run a CLI smoke test." \
  --source-pointer "chat:2026-04-15 user#2"
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

- Do not add raw user-message dumps, images, logs, stack traces, or private data unless the exact text is required.
- Noise reduction may remove non-requirement chatter and duplicates, but it must not delete, flatten, or overcompress the user's actual request.
- Keep the tooling simple: validate required fields, but avoid arbitrary caps or normalization that distorts user wording.
- Never rewrite the whole queue file. Use item-level `add`, `update`, `complete`, or `reject` operations so source pointers, original wording, and order survive.
- Avoid vague one-off labels such as "cleanup"; name the exact requirement set, source range, and intended ledger change.
- Prefer one item per requirement; do not mix status notes, design choices, and implementation steps in one item.
- Use `blocked` only when the next action truly needs a user decision or missing external input.
- Use `complete` or `reject` instead of setting active items to a terminal status; the archive is the terminal-work record.
