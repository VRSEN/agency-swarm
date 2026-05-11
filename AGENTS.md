# Agency Swarm Agent Addendum

Follow the active global machine policy first. This file is a repo addendum only. It may tighten local rules, but it must not weaken user words, mandate limits, evidence gates, privacy, manager-worker boundaries, or public-mutation gates.

If this file conflicts with the global policy, direct user words, or checked remote state, follow the higher-priority source and treat this file as needing repair.

## Repo Baseline

- `CLAUDE.md` must stay a symlink to `AGENTS.md`.
- The default branch is `origin/main`.
- Treat fetched `origin/main` as the baseline for new Agency Swarm work.
- Do not edit dirty user worktrees. For clean-baseline work, use a fresh or owned isolated worktree outside dirty user checkouts, following the global worktree placement rule.
- Hard-reset only fresh or owned isolated worktrees or branches to fetched `origin/main`, and only when they contain no user work.

## Policy And Skills

- Policy, repo-skill, and workflow-rule edits use `.codex/skills/policy-maintenance`.
- Pull-request review, PR compliance, hosted-review fallback, and review-thread work use `.codex/skills/codex-cli-review`.
- Delegation prompts and delegated-output review use `.codex/skills/delegation-management`.
- Requirement tracking uses `.codex/skills/requirement-ledger` as tooling, but durable ledger state must stay outside the repo unless the user explicitly allows repo-local state.
- Claude review may be used only as second-opinion evidence through `.codex/skills/claude-cli-review`; it is not authority.

## Python And Runtime

- Supported Python versions start at 3.12. Development centers on 3.13 while preserving 3.12 compatibility.
- Type hints are mandatory for functions. Use pipe-union syntax instead of legacy union imports.
- Enforce declared types at boundaries. Do not add runtime fallbacks or shape-based branching to accept multiple loose types.
- Keep files under 500 lines unless the user explicitly approves an exception.
- Prefer methods between 10 and 40 lines, and keep them under 100 lines.
- Public modules, functions, and classes should appear before private helpers.

## Tests And Proof

- Unit tests live under `tests/test_*_modules/`. Integration tests live under `tests/integration/`.
- Mirror source layout in tests when practical.
- For runtime changes, run the smallest focused test first, then `make format` and `make check` before commit.
- Run `make ci` before a pull request, merge request, release claim, or repo-wide health claim.
- For docs-only edits, use the docs or markdown check that best matches the touched files, plus `git diff --check`.
- OpenClaw and core `Agent` or `SendMessage` behavior need integration or end-to-end proof with real framework objects unless the change is a tiny pure helper.
- Do not simulate core agent messaging with generic mocks or monkeypatched responses when real framework objects are practical.

## Release Proof

- Before any release or safety claim, run the pre-release review gate required by global policy and the review skill.
- Before any release or safety claim, send a real first message through the installed interface to the maintained local test agency and observe a non-empty streamed response through that same interface.
- Automated auth smoke tests do not replace the installed-interface message proof.
- Any launch, credential, dependency, or interface failure in that proof blocks release until reproduced and root-caused.

## Documentation

- Documentation work follows `.cursor/rules/writing-docs.mdc` when that rule file applies.
- For substantial docs edits, start `cd docs && mintlify dev` before review when practical.
- Before editing docs, read the target page, nearby docs, and relevant source files.
- Introduce features through user benefit before technical setup.
- Prefer product language in user flows unless implementation terms are required.
- Keep full recipes in one place, surface important notes in callouts, and avoid filler.
- Do not mention fork origins in user-facing docs unless the user asks.

## Git And Public Work

- Review `git status -sb` and the final diff before commits or pushes.
- Branch pushes require an explicit mandate. Push policy or feature branches only; do not push `origin/main` directly unless the user explicitly asks.
- No merge, force push, branch deletion, tag, release, package publish, public ready-for-review mark, pull-request creation, GitHub comment, or GitHub review submission is allowed without a direct current mandate for that exact action.
- Treat GitHub `@` mentions as actions that may notify people or trigger automation.
