---
name: test-workflow
description: Use when selecting, writing, reviewing, running, or weighing tests, integration coverage, manual QA, installed-build proof, release proof, live-service validation, and version/path-cache proof in Agency Swarm.
---

# Test Workflow

Use this skill for test strategy, test edits, focused validation, release proof, QA evidence, and deciding whether evidence proves the changed behavior.

## Source Order

- Binding user words are the highest source of truth.
- Ground docs, QA claims, and test expectations in user words, inspected code, `AGENTS.md`, `Makefile`, `pyproject.toml`, existing tests, examples, logs, screenshots, or live behavior.
- Do not invent docs, coverage claims, flows, failures, or manual QA steps that are not grounded in checked evidence.
- Ask when a required behavior, source, credential, artifact, or proof target remains unclear after bounded inspection.

## Proof Selection

- Define the changed behavior boundary before choosing proof: local logic, API or transport boundary, persistence, startup, CLI command, streaming, FastAPI, OpenClaw, docs, release, or user workflow.
- Default to test-driven work for runtime behavior when feasible.
- Unit tests prove local logic. Keep them offline, deterministic, and based on realistic minimal objects.
- Integration or end-to-end tests prove behavior that crosses process, API, transport, persistence, startup, CLI wiring, streaming, workspace, or runtime boundaries.
- Unit tests are not acceptable proof for pure integration behavior.
- OpenClaw behavior requires integration or end-to-end coverage unless the code is a tiny pure helper.
- Core Agent Messaging, including `Agent`, `SendMessage`, handoff, and message routing, must not be proven with generic mocks or fabricated response simulation.
- Pull-request checks and unit tests are useful evidence, but they do not replace end-user proof when the report came from a user-visible flow.
- When persisted state, queued work, history, SDK payloads, UI state, or similar internal state crosses a process, API, or transport boundary, prove both local behavior and the exact serialized outbound payload or boundary contract.
- For docs-only, policy-only, or formatting-only edits, use a formatter, linter, rendered check, or `git diff --check` instead of runtime tests.
- Do not continue if a required command fails.

## Bug Proof

- Reproduce the reported failure before fixing it when practical.
- Add or extend an automated test that fails for the report before runtime code changes when practical.
- Rerun the exact failed flow against the same kind of build or artifact and starting state before calling the bug fixed.
- CLI bugs need the exact command against the released build, a fresh local install, or the same wrapper the user ran.
- Browser, visual, or generated-UI bugs need a screenshot or rendered output from the user-visible build; text-only dumps do not close visual bugs.
- Do not claim a fix is done, and do not close a requirement, until end-user proof exists and is cited.

## Agency Swarm Behavior Proof

- For `Agent`, `Agency`, `SendMessage`, handoffs, message routing, streaming, FastAPI, and OpenClaw, prefer real framework objects and typed dependency models over generic mocks.
- Prove routing behavior at the protocol or API boundary by asserting captured request or response payloads, not only internal helper calls.
- For file uploads, attachments, persistence, model settings, or context overrides, prove the serialized outbound contract and the local state transition.
- For provider-specific integrations or live services, run full related coverage when needed credentials exist; key-based skips are not proof.
- If planned validation needs a real LLM or live service, verify credentials and access before asking the user for keys or permission.

## Test Writing

- Keep each test function about 100 lines or less.
- Test behavior, not private implementation details, unless the private boundary is the only reliable proof target.
- Use real framework objects and the real implementation when practical.
- Avoid mocks unless they isolate an external dependency that is not the behavior under test.
- Do not copy production logic into tests.
- Prefer extending nearby tests over adding new test files unless nearby tests cannot cleanly cover the behavior.
- Put unit tests under `tests/test_*_modules/` and integration tests under `tests/integration/`, mirroring the source layout.
- Do not duplicate the same proof across unit and integration levels.
- Retire unit tests that hide gaps in real behavior.
- Use precise assertions in one clear order; avoid OR logic in assertions.
- Use stable, descriptive test names.
- Use isolated file systems and temporary directories.
- Avoid hardcoded temp paths or ad hoc directories.
- Avoid slow or hanging tests. If a skip is necessary, leave a clear `FIXME`.
- Remove dead code you find while testing when it is in scope.
- Do not claim to fix flakiness unless you observed and documented the flake.
- Aim for 90% test coverage or better when coverage is in scope.

## Commands And Credentials

- Use `uv`, project virtual environments, and the repo `Makefile`; do not use global Python tools when repo tooling can run the check.
- Run the smallest high-signal focused command first, usually `uv run pytest <path>` or `uv run pytest <path>::<test_name>`.
- If you modify a module, run its focused tests.
- If you modify an example, run it when it is non-interactive.
- Run `make format` after code or docs changes unless the task is read-only or the change is policy-only and a diff check is the better proof.
- Run `make check` before staging, committing, pushing, or asking for review.
- Run `make ci` before a pull request, merge-readiness claim, release-readiness claim, or repository-wide health claim.
- For long-running commands, use timeouts that match the real wait window instead of stopping early.
- For package, CLI, or installed-build behavior, test from a fresh shell so shell hash tables and cached wrappers cannot hide stale paths.

## Manual QA

- Use manual QA only when automation cannot honestly prove the user path within the mandate or when the release gate requires the user to test the local build.
- Write the manual QA target before running it: artifact, command, environment, starting state, expected visible result, and failure evidence to capture.
- Manual QA for visual, browser, or terminal behavior must capture a screenshot, rendered output, or terminal transcript from the installed or user-visible build.
- Manual QA does not replace automated coverage when the behavior is stable enough to test.
- Record any manual gap in the checked-in owner for that flow, or escalate if no owner exists.

## Installed Package And Version Proof

- Before saying a local installed package or CLI is updated, verify from a fresh shell that the exact command the user will run resolves to the expected path and version.
- Check likely command names and wrappers for this repo, including `agency-swarm`, `uv run agency-swarm`, `python -m agency_swarm.cli.main`, package-manager shims, shell hash tables, and cached binaries when they can affect the user command.
- Prove that no package manager, cache, PATH entry, symlink, or wrapper returns an older published version.
- Record the resolved command path, version output, package source when relevant, and the fresh-shell command used.
- If a wrapper or package manager still resolves to an older published version, do not claim the local install is updated; fix the install path or escalate with the exact stale resolver.

## Release Proof

- Before release approval, prove the exact release commit satisfies the live repo gates and relevant workflow runs for its ref, or their local equivalents when GitHub cannot run them.
- Required local release proof includes `make format`, `make check`, `make ci`, docs lint when applicable, and focused behavior proof for every changed release path.
- Before any release or safety claim, build and reinstall the package from the fresh local build so the user's normal command points to it.
- Verify installed package and version proof from a fresh shell before handing the build to the user.
- Launch the fresh installed interface against the maintainer's canonical local test agency, send a real first message through the connected conversation, and verify that a non-empty streaming assistant response renders.
- Auth-smoke CI alone never passes the release proof gate.
- Any launch failure blocks release proof until the root cause is reproduced.
