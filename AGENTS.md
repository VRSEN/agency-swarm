# Agency Swarm Repository Addendum

Core principle, in the maintainer's words: "Agency Swarm should remain a focused orchestration layer over the OpenAI Agents SDK, not grow into a duplicate agent runtime. Whenever possible, use the OpenAI Agents SDK instead of reimplementing its behavior." Every change is checked against it.

This file contains only repository-specific addenda to the controlling machine-global policy and matching global skills.

## 1. Repository Baseline

1.1 The canonical remote-tracking default branch is `origin/main`.
1.2 `CLAUDE.md` must remain a symlink to `AGENTS.md`; verify it before relying on repository policy or shipping a repository-policy change.
1.3 Shared policy from `VRSEN/agentswarm-cli` may appear here only as a strict subset or a necessary Python/Agency adaptation; omit CLI, TUI, OpenCode, Bun, npm, and package-layout rules without a Python or Agency equivalent.
1.4 If an active pull request duplicates an open Dependabot dependency update, close the Dependabot pull request through the normal public-mutation approval path.
1.5 Commits and pull requests carry no AI attribution: no AI `Co-Authored-By` trailers and no "Generated with" footers in commit messages, pull request titles, or pull request descriptions.
1.6 If functionality is now implemented upstream, remove the custom implementation unless there is a concrete reason to keep it. If the custom implementation differs from upstream in a way that looks artificial, incorrect, or non-standard, escalate to the user with a recommendation to delete it and reuse upstream behavior.
1.7 Third-party or vendor integrations live outside this repository: decline vendor-pitch issues and pull requests with a pointer to the existing extension seam, and ship at most a docs recipe.
1.8 Backward compatibility is not a constraint: take the best target design, and ship breaking changes under a new major or minor version with a breaking-changes note.

## 2. Repository Commands And Review Artifacts

2.1 Use `make prime` when repository-structure discovery adds value.
2.2 Run `make format` before a commit when its touched files are covered by repository formatting.
2.3 Run `make check` before staging or committing runtime, interface, or integration changes.
2.4 Run `make ci` before a release, a broad or risky merge-readiness claim, a repository-wide health claim, or when focused proof cannot bound risk.
2.5 Use project virtual environments and repository task runners, not global interpreters or absolute paths.
2.6 The general review gate is an independent review by a different live model through the currently allowed route in the global worker-model-routing allowlist, at `high` reasoning effort, against `origin/main`.
2.7 The policy review gate uses the same route at `xhigh` reasoning effort.
2.8 The pre-release review gate uses the same route at `xhigh` reasoning effort against the exact release commit.
2.9 Broad, public, high-risk, or low-confidence repository-policy edits require a clean policy review before shipping; `high` is insufficient.
2.10 When the primary review route cannot be used, fall back only to another currently-allowed route with the same `origin/main` base and reasoning class.
2.11 Save pre-release and fallback review output to the owning task's artifacts directory, never `/tmp`.
2.12 Supporting reviews may supplement but never replace a required independent review.

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
4.12 Keep terminology self-consistent: code identifiers, internal symbols, comments, user-facing copy, and documentation use the same product vocabulary (for example, canonical mode names), and each change's polishing pass includes a terminology-consistency check.

## 5. Tests And Runtime-Specific Proof

5.1 Canonical unit tests live under `tests/test_*_modules/`; integration tests live under `tests/integration/`; both mirror source layout.
5.2 Keep each test under 100 lines when practical.
5.3 High-level OpenClaw runtime behavior requires integration or end-to-end coverage unless the changed code is a tiny pure helper.
5.4 Do not cover OpenClaw runtime behavior with mock-heavy unit tests.
5.5 Validate Core Agent Messaging through real framework objects; do not simulate `Agent` or `SendMessage` with generic mocks or monkeypatched responses.

## 6. Release Specifics

6.1 A release or safety claim requires a clean pre-release review (2.8) against the exact release commit.
6.2 Before a release or safety claim, send a real first message through the installed interface to the maintained local test agency and observe a non-empty streamed response through that interface.
6.3 Automated authentication smoke tests do not satisfy the installed-interface proof in 6.2.
6.4 A launch, credential, dependency, or interface failure in that proof blocks the release claim until it is reproduced and root-caused.
6.5 Keep user-facing bugfix release cuts minimal and exclude repository-policy edits and tooling churn.
6.6 Ship repository-policy edits directly to the default branch after exact approval, never inside a public product pull request or user-facing release.
6.7 A release claim requires per-commit evidence on the release page: every change since the previous release names its test evidence and confidence level.
6.8 Existing behavior affected by a change must be regression-tested end-to-end, and the previous and new releases compared, before merge or release.
6.9 No test may be skipped in the final pre-release suite; tests requiring real API keys run with real keys. A single skipped test blocks the release claim.
6.10 Nothing is tagged, published as a GitHub release, or uploaded to PyPI without the maintainer's explicit approval; agents prepare release drafts only.
6.11 After upgrading `openai-agents`, LiteLLM, or a provider SDK, run an end-to-end test that makes a tool call or delegation and then sends the resulting history back to the model in a following turn.
