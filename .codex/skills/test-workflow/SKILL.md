---
name: test-workflow
description: Use when selecting, writing, reviewing, running, or weighing tests, integration coverage, manual QA, installed-build proof, release proof, and live-service validation in agency-swarm.
---

# Test Workflow

Use this skill for test strategy, test edits, focused validation, release proof, QA evidence, and deciding whether evidence proves the changed behavior.

## Source Order

- Binding user words are the highest source of truth.
- Ground docs, QA claims, and test expectations in user words, inspected code, existing tests, logs, screenshots, or live behavior.
- Do not invent docs, coverage claims, flows, failures, or manual QA steps that are not grounded in checked evidence.
- Ask when a required behavior, source, credential, artifact, or proof target remains unclear after bounded inspection.

## Proof Selection

- Define the changed behavior boundary before choosing proof: local logic, process boundary, API boundary, persistence, startup, CLI wiring, streaming, release, or user workflow.
- Default to test-driven work for runtime behavior when feasible.
- Unit tests prove local logic. Keep them offline, deterministic, and based on realistic minimal objects.
- Integration or end-to-end tests prove behavior that crosses process, API, persistence, startup, CLI, streaming, workspace, or runtime boundaries.
- Unit tests are not acceptable proof for pure integration behavior.
- Pull-request checks and unit tests are useful evidence, but they do not replace end-user proof when the report came from a user-visible flow.
- For docs-only or formatting-only edits, use a formatter or linter instead of runtime tests.
- Do not continue if a required command fails.

## Bug Proof

- Reproduce the reported failure before fixing it.
- Add or extend an automated test that fails for the report before runtime code changes when feasible.
- Rerun the exact failed flow against the same kind of build or artifact and starting state before calling the bug fixed.
- CLI bugs need the exact command against the installed or freshly built package when possible.
- Do not claim a fix is done, and do not close a requirement, until end-user proof exists or the blocker is stated.

## Commands

- Use `make format` for formatting and safe lint fixes.
- Use `make check` for lint and type checking.
- Use focused `uv run pytest <path>` runs while debugging.
- Use `make ci` before pull requests, merge-readiness claims, or repo-wide health claims.
- Use `make coverage` when coverage is part of the mandate.
- For live-provider paths, inspect credentials first and stop if real validation is required but credentials are unavailable.

## Output

- State the smallest proof that closes the changed boundary.
- State failed or skipped validation plainly with the reason.
- Do not add a separate validation section to user-facing replies when one concise sentence is enough.
