---
name: claude-cli-review
description: Use when Claude CLI is the chosen local review worker for a bounded diff review or extraction pass and a saved /tmp artifact is required.
---

# Claude CLI Review

Use Claude CLI only when `AGENTS.md` and Tool And Model Policy allow it. Treat it as weaker evidence than GPT-5.5; managers must verify its output before final decisions.

The current repo-approved Claude review model is Claude Opus 4.7. Keep the concrete CLI model ID in the health-check command variable below so future model updates have one obvious edit point.

## Health Check

```bash
CLAUDE_REVIEW_MODEL=claude-opus-4-7
claude -p --model "$CLAUDE_REVIEW_MODEL" --effort high "Reply exactly with: ok"
```

Expected output: `ok`.

## Review Pattern

1. Build a bounded prompt from the relevant diff or files.
2. Run Claude non-interactively with a timeout.
3. Save stdout and stderr to `/tmp/claude_review_<short_sha>.txt`.
4. If the shell pipeline hangs or produces an empty file, rerun through a small Python `subprocess.run(...)` wrapper with a hard timeout.

Prompt shape:

```text
Review this git diff for real correctness, regression, security, data-boundary, policy, repo-rule, PR compliance, review-gate, test/QA evidence, excessive-scope, and unintentional-drift issues. Treat real issues as P0/P1/P2 findings by risk under AGENTS.md. Ignore style nits. Return exactly "No findings." if clean.
```

## Scope Control

- Prefer the smallest diff that proves the question.
- Keep docs and lockfile noise out unless the user asked for docs review.
- Review high-risk runtime paths first: identity, persistence, streaming, tool calls, release wiring, and tests.

## Output

Report whether Claude returned `No findings.`, whether it timed out, and any concrete findings with file paths.
