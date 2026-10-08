# Agency Swarm Repository Rules

Core principle, in the maintainer's words: "Agency Swarm should remain a focused orchestration layer over the OpenAI Agents SDK, not grow into a duplicate agent runtime. Whenever possible, use the OpenAI Agents SDK instead of reimplementing its behavior." Check every change against it.

This file adds repository rules to the machine-global policy. It never weakens that policy.

## 1. The OpenAI Agents SDK comes first

1.1 Before you write or change code, find how the `openai-agents` version pinned in `pyproject.toml` already does it. Read its installed source (`.venv/.../site-packages/agents`), its docs, and `references/openai-agents-python` checked out at that tag. Clone it there first if it is missing.
1.2 If the SDK has it, use it: call it, configure it, or subclass it. Do not copy its logic. Do not write a parallel version.
1.3 Write custom code only when the SDK has no equivalent. The pull request MUST name the SDK feature you checked and say why it does not fit.
1.4 Code that wraps or replaces an SDK abstraction (session, history items, streaming events, model settings, tracing, guardrails, handoffs) MUST name the SDK class it mirrors in its docstring. It MUST support every feature of that class, or list each unsupported feature with the reason.
1.5 When the SDK adds a feature that our code duplicates, delete our code and use the SDK's in the same change. If the deletion breaks the public API, deprecate our code instead and remove it in the next major version (2.1). Keep our code only for a concrete reason written in the pull request.
1.6 When custom code behaves differently from the SDK in a way that looks accidental, propose to the maintainer to delete it and use the SDK.
1.7 Each `openai-agents` upgrade MUST check the SDK changelog against every wrapper from 1.4. List each new SDK feature a wrapper does not support in the upgrade pull request. A GitHub issue for it follows 2.2.
1.8 Third-party and vendor integrations stay outside this repository. Decline vendor-pitch issues and pull requests, point to the existing extension seam, and ship at most a docs recipe.

## 2. Users and public actions

2.1 Keep backward compatibility. Ship a breaking change only when it is necessary, only in a new major version, and always with a breaking-changes note.
2.2 Get the maintainer's approval of the exact text or action before any public action on GitHub: comments, reviews, issues, pull requests, merges, closes, reopens, labels, pushes to shared branches, tags, releases and package uploads. Prepare drafts. Exception: a short reply that corrects a clearly wrong automated comment.
2.3 Put no AI attribution in commits or pull requests: no AI `Co-Authored-By` trailers and no "Generated with" footers.

## 3. Repository basics

3.1 The default branch is `origin/main`.
3.2 `CLAUDE.md` MUST stay a symlink to `AGENTS.md`. Check it before you ship a change to this file.
3.3 Use the project virtual environment and the `make` targets, never a global interpreter.
3.4 Run `make format` before each commit. Run `make check` before you commit a runtime, interface or integration change.
3.5 Run `make ci` before a release, before a claim that a broad or risky change is ready to merge, and after each upgrade of `openai-agents`, LiteLLM or a provider SDK.
3.6 Use `make prime` to map the repository structure when you need it.

## 4. Review

4.1 Every change gets a review against `origin/main` by a different model than the one that wrote it.
4.2 A change to this file, and each release commit, gets its review from the strongest model available that did not write it. The pre-release review runs on the exact release commit.
4.3 Save pre-release review output with the release evidence, never in `/tmp`.

## 5. Code

5.1 Support Python 3.12 and later. Develop on 3.13.
5.2 Type every function. Use `X | Y` unions.
5.3 Enforce declared types at boundaries. Where a declared type exists, do not use `Any`, duck typing, runtime shape checks or fallbacks that accept several types. Do not use type ignores in production code.
5.4 Use the SDK's typed models and the dependency's own types. Read them and the code next to your change before you edit.
5.5 Put imports at the top of the file. Fix a circular import by restructuring, not by a local import. If a local import is necessary, say why in a comment.
5.6 A file stays under 500 lines unless the maintainer approves more. When you edit a larger file, keep your change small and make the file smaller in the same change, unless the maintainer approves otherwise.
5.7 Keep methods between 10 and 40 lines, and always under 100.
5.8 Use one name for one thing everywhere: code, comments, user-facing text and docs.
5.9 When a dependency requirement or resolved version changes, update every affected lockfile in the same change.

## 6. Tests

6.1 Unit tests live in `tests/test_*_modules/`. Integration tests live in `tests/integration/`. Both mirror the source layout.
6.2 Keep test coverage at 90% or more. Keep each test under 100 lines when practical.
6.3 Test agent messaging (`Agent`, `SendMessage`) and OpenClaw runtime behavior through real framework objects and integration or end-to-end tests, not generic mocks. A small pure helper needs only unit tests.
6.4 Each change to existing behavior gets an end-to-end regression test before merge.
6.5 After an upgrade of `openai-agents`, LiteLLM or a provider SDK, the suite MUST include an end-to-end test that makes a tool call or delegation and then sends that history back to the model in the next turn.

## 7. Documentation

7.1 Follow `.cursor/rules/writing-docs.mdc`.
7.2 Before review of a large docs change, run `cd docs && mintlify dev` and say that the preview runs.
7.3 Do not mention fork origins in user-facing docs unless the maintainer asks.

## 8. Releases

8.1 A release or safety claim needs a clean review (4.2) of the exact release commit.
8.2 Before the claim, send a real first message through the installed interface to the maintained local test agency and see a non-empty streamed response. An automated authentication smoke test does not count.
8.3 A launch, credential, dependency or interface failure in that check blocks the claim until it is reproduced and its root cause is known.
8.4 Run the final pre-release suite with no skipped test. Tests that need real API keys run with real keys. One skipped test blocks the release.
8.5 The release page lists every change since the previous release with its test evidence and a confidence level (high, medium or low).
8.6 Compare the previous and new release on the behavior each change affects.
8.7 Keep bugfix releases minimal: no policy edits and no tooling churn.
8.8 Ship changes to this file directly to the default branch after the maintainer approves the exact text. Never put them in a product pull request or a release.
