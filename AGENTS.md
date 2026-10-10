# Agency Swarm Repository Rules

Core principle, in the maintainer's words: "Agency Swarm should remain a focused orchestration layer over the OpenAI Agents SDK, not grow into a duplicate agent runtime. Whenever possible, use the OpenAI Agents SDK instead of reimplementing its behavior." Check every change against it.

Multi-step procedures live in `.claude/skills/`: `review`, `release`, `sdk-upgrade`. Load the matching skill before you start one of those.

## 1. The OpenAI Agents SDK comes first

1.1 Before you write or change code, find how the `openai-agents` version pinned in `pyproject.toml` already does it: read its installed source in `.venv` and `references/openai-agents-python` at that tag (clone it there if missing). If the SDK has it, call it, configure it or subclass it. Never copy its logic or write a parallel version.
1.2 Write custom code only when the SDK has no equivalent. The pull request names the SDK feature you checked and why it does not fit.
1.3 Code that wraps or replaces an SDK abstraction (session, history items, streaming events, model settings, tracing, guardrails, handoffs) names the SDK class it mirrors in its docstring and supports every feature of that class, or lists each unsupported feature with the reason. A custom session layer once missed SDK compaction for months; this rule exists so that does not repeat.
1.4 When the SDK adds a feature our code duplicates, delete our code and use the SDK's in the same change. Keep our version only for a concrete reason written in the pull request.
1.5 Third-party and vendor integrations stay outside this repository. Decline vendor-pitch issues and pull requests, point to the extension seam, and ship at most a docs recipe.

## 2. Moving fast and public actions

2.1 Backward compatibility is not a goal by itself. Make the better change, bump the version, and document what changed in the release notes and migration guide. Do not add compatibility shims. Escalate to the maintainer only a change that breaks users who cannot upgrade, such as an old deployed template.
2.2 Get the maintainer's approval of the exact text or action before any public action on GitHub: comments, reviews, issues, pull requests, merges, closes, labels, pushes to shared branches, tags, releases and package uploads. Prepare drafts. Exception: a short reply that corrects a clearly wrong automated comment.
2.3 No AI attribution in commits or pull requests: no AI `Co-Authored-By` trailers, no "Generated with" footers.

## 3. Tooling

3.1 Use the project virtual environment and the `make` targets, never a global interpreter.
3.2 Run `make format` before each commit and `make check` before you commit a runtime, interface or integration change. Run `make ci` before you claim a broad or risky change is ready to merge.
3.3 `CLAUDE.md` stays a symlink to `AGENTS.md`.

## 4. Code

4.1 Support Python 3.12 and later; develop on 3.13.
4.2 Type every function with `X | Y` unions. Where a declared type exists, do not use `Any`, duck typing, runtime shape checks or fallbacks that accept several types. No type ignores in production code. Use the SDK's typed models and each dependency's own types.
4.3 Imports go at the top of the file. Fix a circular import by restructuring; a necessary local import carries a comment that says why.
4.4 Keep files under 500 lines and methods under 40 lines. When you touch a larger file, make it smaller in the same change.
4.5 Use one name for one thing everywhere: code, comments, user-facing text and docs.
4.6 When a dependency requirement or resolved version changes, update every affected lockfile in the same change.

## 5. Tests

5.1 Unit tests live in `tests/test_*_modules/`, integration tests in `tests/integration/`; both mirror the source layout. Keep coverage at 90% or more.
5.2 Test agent messaging (`Agent`, `SendMessage`) and OpenClaw runtime behavior through real framework objects in integration or end-to-end tests, not generic mocks. A small pure helper needs only unit tests.
5.3 A change to existing behavior ships with a test that fails without it.

## 6. Documentation

6.1 Follow `.cursor/rules/writing-docs.mdc`. Preview a large docs change with `cd docs && mintlify dev` before review.
6.2 Do not mention fork origins in user-facing docs unless the maintainer asks.
