# Agency Swarm Agent Supplement

/Users/nick/.codex/AGENTS.md is the only operating contract. This file is a local supplement for `VRSEN/agency-swarm`; it must stay strictly aligned with that global contract and with `VRSEN/agentswarm-cli/AGENTS.md`.

`CLAUDE.md` must remain a symlink to `AGENTS.md`.

## Local Scope

- The default branch for this repo is `origin/main`.
- Keep repo-specific commands, testing, QA, release, docs-preview, and workflow procedures in repo skills under `.codex/skills/**`.
- Use `.codex/skills/policy-maintenance` for policy, repo-skill, and workflow-rule edits.
- Use `.codex/skills/requirement-ledger` for durable queue, archive, work-state, and artifact tracking.
- Use `.codex/skills/delegation-management` before scoped subagent prompts, worker reuse decisions, or delegated-output review.
- Use `.codex/skills/codex-cli-review` for pull-request review loops, review artifacts, and release-readiness review.
- Use `.codex/skills/test-workflow` for test selection, test writing, QA, docs-preview checks, examples, live-service proof, and release proof.

## Code And Docs

- Python support starts at 3.12; active development centers on 3.13.
- Type hints are mandatory for functions; use pipe-union syntax.
- Documentation work follows `.cursor/rules/writing-docs.mdc`.
- Do not mention fork origins in user-facing docs unless the user asks.
