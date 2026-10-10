---
name: review
description: Review a change against origin/main before it merges. Use for every pull request, for each edit of AGENTS.md, and for a release commit.
---

# Review a change

Every change gets a review against `origin/main` by a different model than the one that wrote it. A change to `AGENTS.md` and each release commit get their review from the strongest model available that did not write it.

## Steps

1. Diff the branch against `origin/main`. Read the whole diff, not only the files the author named.
2. Check the core principle first: does the change use the OpenAI Agents SDK where it could, or does it reimplement SDK behavior? A wrapper around an SDK abstraction names the SDK class in its docstring and supports every feature of that class or lists each gap with a reason (AGENTS.md 1.3).
3. Check the repository rules in `AGENTS.md`: typing at boundaries, no fallbacks that accept several types, imports at the top, file and method size, one name for one thing, lockfiles updated with dependency changes.
4. Check tests: a change to existing behavior has a test that fails without it; agent messaging and OpenClaw runtime changes are tested through real framework objects, not generic mocks; coverage stays at 90% or more.
5. Run `make check`. For a runtime, interface or integration change, also run `make tests`. For a broad or risky change, run `make ci`.
6. Report findings ranked by severity, each with the file, the line and the concrete failure it causes. Say plainly when nothing was found.

A review comment, approval or merge on GitHub is a public action: the maintainer approves the exact text or action first (AGENTS.md 2.2).
