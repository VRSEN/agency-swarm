# Agency Swarm Repository Addendum

This file contains only repository-specific addenda to the controlling machine-global policy and matching global skills.

## 1. Repository Baseline

1.1 The canonical remote-tracking default branch is `origin/main`.
1.2 `CLAUDE.md` must remain a symlink to `AGENTS.md`; verify it before relying on repository policy or shipping a repository-policy change.
1.3 Shared policy from `VRSEN/agentswarm-cli` may appear here only as a strict subset or a necessary Python/Agency adaptation; omit CLI, TUI, OpenCode, Bun, npm, and package-layout rules without a Python or Agency equivalent.
1.4 If an active pull request duplicates an open Dependabot dependency update, close the Dependabot pull request through the normal public-mutation approval path.

## 2. Repository Commands And Review Artifacts

2.1 Use `make prime` when repository-structure discovery adds value.
2.2 Run `make format` before a commit when its touched files are covered by repository formatting.
2.3 Run `make check` before staging or committing runtime, interface, or integration changes.
2.4 Run `make ci` before a release, a broad or risky merge-readiness claim, a repository-wide health claim, or when focused proof cannot bound risk.
2.5 Use project virtual environments and repository task runners, not global interpreters or absolute paths.
2.6 The general Codex review command is `codex review --base origin/main -c model_reasoning_effort="high"`.
2.7 The policy Codex review command is `codex review --base origin/main -c model_reasoning_effort="xhigh"`.
2.8 The pre-release Codex review command is `codex review --base origin/main -c model_reasoning_effort="xhigh"`.
2.9 Broad, public, high-risk, or low-confidence repository-policy edits require a clean policy Codex review before shipping; that review uses `gpt-5.6-sol` (the Codex CLI default) or an approved substitute with `xhigh` reasoning; `high` is insufficient.
2.10 When the review command cannot be used, fall back only to an equivalent `codex exec` diff review with the same `origin/main` base and reasoning class.
2.11 Save pre-release and fallback review output to `/tmp/codex_review_<short_sha>.txt`.
2.12 Supporting reviews may supplement but never replace a required Codex review.

## 3. Documentation

3.1 Documentation work follows `.cursor/rules/writing-docs.mdc`.
3.2 Before review of substantial documentation work, start `cd docs && mintlify dev` and state that the preview is running.
3.3 Do not mention fork origins in user-facing docs unless the user asks.

## 4. Python, Types, And File Discipline

4.1 Supported Python versions start at 3.12; development centers on 3.13 while preserving 3.12 compatibility.
4.2 Use pipe-union syntax, not legacy union imports, and type every function.
4.3 Enforce declared types at boundaries; do not add runtime fallbacks or shape-based branching to accept multiple types.
4.4 Do not use `Any`, duck typing, or runtime field checks where proper types exist, and avoid type ignores in production code.
4.5 Prefer authoritative typed dependency models and inspect dependency types and adjacent patterns before changing runtime code.
4.6 Prefer top-level imports; call out any necessary local import and restructure circular dependencies instead of hiding them with local-import workarounds.
4.7 No file may exceed 500 lines without explicit user approval.
4.8 Prefer methods between 10 and 40 lines and keep them under 100 lines.
4.9 Target test coverage of at least 90%.
4.10 When editing an oversized file, keep the net change minimal and reduce its size in the same change unless the user approves otherwise.
4.11 When dependency requirements or resolved versions change, update every affected lockfile in the same change.

## 5. Tests And Runtime-Specific Proof

5.1 Canonical unit tests live under `tests/test_*_modules/`; integration tests live under `tests/integration/`; both mirror source layout.
5.2 Keep each test under 100 lines when practical.
5.3 High-level OpenClaw runtime behavior requires integration or end-to-end coverage unless the changed code is a tiny pure helper.
5.4 Do not cover OpenClaw runtime behavior with mock-heavy unit tests.
5.5 Validate Core Agent Messaging through real framework objects; do not simulate `Agent` or `SendMessage` with generic mocks or monkeypatched responses.

## 6. Release Specifics

6.1 A release or safety claim requires a clean pre-release Codex review against the exact release commit.
6.2 Before a release or safety claim, send a real first message through the installed interface to the maintained local test agency and observe a non-empty streamed response through that interface.
6.3 Automated authentication smoke tests do not satisfy the installed-interface proof in 6.2.
6.4 A launch, credential, dependency, or interface failure in that proof blocks the release claim until it is reproduced and root-caused.
6.5 Keep user-facing bugfix release cuts minimal and exclude repository-policy edits and tooling churn.
6.6 Ship repository-policy edits directly to the default branch after exact approval, never inside a public product pull request or user-facing release.
