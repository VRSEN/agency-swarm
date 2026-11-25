# Agency Swarm Repository Rules

Agency Swarm is a focused orchestration layer over the OpenAI Agents SDK. It does not grow into
a second agent runtime: where the SDK already does something, this repository uses the SDK.
Check every change against that principle.

`CONTRIBUTING.md` holds the setup, the checks and two procedures: an SDK upgrade and a release.
Follow the procedure before you start one of those.

## 1. The OpenAI Agents SDK comes first

- 1.1 Before you write or change code, find how the `openai-agents` version pinned in
  `pyproject.toml` already does it: read its installed source in `.venv`. If the SDK has it,
  call it, configure it or subclass it. Do not copy its logic or write a parallel version.
- 1.2 Write custom code only when the SDK has no equivalent. The pull request names the SDK
  feature you checked and why it does not fit.
- 1.3 Code that wraps or replaces an SDK abstraction (session, history items, streaming events,
  model settings, tracing, guardrails, handoffs) names the SDK class it mirrors in its docstring
  and supports every feature of that class, or lists each unsupported feature with the reason.
- 1.4 When the SDK adds a feature our code duplicates, delete our code and use the SDK's in the
  same change. Keep our version only for a concrete reason written in the pull request.
- 1.5 Third-party and vendor integrations live outside this repository. The docs may carry a
  short recipe for one.

## 2. Releases and public actions

- 2.1 A breaking change ships with a version bump and an entry in the release notes and
  `docs/migration/guide.mdx`.
- 2.2 The maintainer approves merges, tags, releases and package uploads.

## 3. Tooling

- 3.1 Use `uv` and the `make` targets, not a global interpreter.
- 3.2 Run `make format` before each commit and `make check` before you commit a runtime,
  interface or integration change. Run `make ci` before you call a broad or risky change
  ready to merge.
- 3.3 `CLAUDE.md` stays a symlink to `AGENTS.md`.

## 4. Code

- 4.1 Support Python 3.12 and later, as `pyproject.toml` requires; develop on 3.13.
- 4.2 Type every function with `X | Y` unions. Where a declared type exists, do not use `Any`,
  duck typing, runtime shape checks or fallbacks that accept several types. Do not add type
  ignores under `src/`. Use the SDK's typed models and each dependency's own types.
- 4.3 Imports go at the top of the file. Fix a circular import by restructuring; a necessary
  local import carries a comment that says why.
- 4.4 Keep files under 500 lines and methods under 40 lines. When you touch a larger file, make
  it smaller in the same change.
- 4.5 Use one name for one thing everywhere: code, comments, user-facing text and docs.
- 4.6 When a dependency requirement or resolved version changes, update `uv.lock` in the same
  change.

## 5. Tests

- 5.1 Unit tests live in `tests/test_*_modules/`, integration tests in `tests/integration/`;
  both mirror the source layout. `make coverage` fails below 90%.
- 5.2 Test agent messaging (`Agent`, `SendMessage`) and OpenClaw runtime behavior through real
  framework objects in integration or end-to-end tests, not generic mocks. A small pure helper
  needs only unit tests.
- 5.3 A change to existing behavior ships with a test that fails without it.

## 6. Documentation

- 6.1 Follow `.cursor/rules/writing-docs.mdc`. Preview a large docs change locally with the
  Mintlify CLI before review.
