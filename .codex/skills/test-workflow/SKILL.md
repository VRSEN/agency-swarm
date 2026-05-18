---
name: test-workflow
description: Use when selecting, writing, reviewing, running, or weighing tests, examples, docs-preview checks, manual QA, live-service proof, and release proof in agency-swarm.
---

# Test Workflow

Use this skill for test strategy, focused validation, QA evidence, examples, docs-preview checks, live-service proof, and release proof.

## Source Order

- Binding user words are the highest source of truth.
- Ground test expectations and QA claims in inspected code, docs, examples, logs, screenshots, live behavior, or user reports.
- Ask only when a required behavior, source, credential, artifact, or proof target remains unclear after bounded inspection.

## Proof Selection

- Define the changed boundary before choosing proof: local logic, agent runtime, messaging, streaming, tool use, examples, docs, package behavior, or release.
- Default to test-driven work for runtime behavior when feasible.
- Unit tests prove local logic. Integration or end-to-end tests prove behavior across agent messaging, streaming, tools, examples, live services, package boundaries, or release flows.
- Changes to `Agent`, `SendMessage`, `OpenClaw`, streaming, examples, package behavior, or release behavior need integration, end-to-end, example, installed-package, or release proof that matches the changed path before they are called done.
- For docs-only or formatting-only edits, use a formatter, docs lint, rendered check, or focused reread instead of runtime tests.
- Do not continue if a required command fails.

## Bug Proof

- Reproduce the reported failure before fixing it when practical.
- Add or extend an automated test that fails for the report before runtime code changes when practical.
- Rerun the exact failed user flow, command, or example before calling the bug fixed.
- Do not close a requirement until end-user proof exists or a concrete blocker is recorded.

## Test Writing

- Keep tests deterministic, offline when practical, and behavior-focused.
- Prefer extending nearby tests over adding new files.
- Use real framework objects when practical.
- Avoid mocks unless they isolate an external service that is not under test.
- Do not copy production logic into expected values.
- Keep unit tests under `tests/test_*_modules/` and integration tests under `tests/integration/`, mirroring source layout when practical.
- Target test coverage at ninety percent or higher.

## Commands

- Use the project virtual environment and repo task runner.
- Run `make prime` when structure discovery adds value.
- Run the smallest high-signal focused test first.
- Run `make format` before staging or committing.
- Run `make check` before staging or committing.
- Run `make ci` before pull requests, merges, releases, or repo-wide health claims.
- For Requirement Ledger script changes, run `python .codex/skills/requirement-ledger/scripts/test_requirement_ledger.py`.
- If you modify an example, run that example or a non-interactive equivalent.
- For long-running commands, use a timeout that matches the real wait window.

## Docs

- Follow `.cursor/rules/writing-docs.mdc` for documentation changes.
- Before substantial docs review, run `cd docs && mintlify dev` when the environment supports it and state whether it is running.
- Read the target page, nearby docs, relevant code, and official references before adding or moving docs content.
- Keep docs focused on user benefit first, then the needed technical steps.

## Live Services And Credentials

- If planned proof needs a real model provider or live service, inspect local environment sources before saying credentials are missing.
- When usable credentials exist, run the related integration or example coverage.
- Do not treat a credential-based skip as proof when live coverage is required.

## Release Proof

- Before a release or release-safety claim, run the relevant local proof, including `make ci` and any focused examples or integration suites for changed behavior.
- Send a real first message through the installed interface to the maintained local test agency and observe a non-empty streamed response.
- Automated auth smoke alone does not satisfy release proof.
- Any launch, credential, dependency, or interface failure blocks release proof until it is reproduced and root-caused.
