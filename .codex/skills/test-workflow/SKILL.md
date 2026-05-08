---
name: test-workflow
description: Use when selecting, writing, reviewing, running, or weighing tests, integration coverage, manual QA, installed-build proof, release proof, live-service validation, and version/path-cache proof in agency-swarm.
---

# Test Workflow

Use this skill for test strategy, test edits, focused validation, release proof, QA evidence, and deciding whether evidence proves the changed behavior.

## Source Order

- Binding user words are the highest source of truth.
- Ground docs, QA claims, and test expectations in user words, inspected code, docs, examples, existing tests, logs, screenshots, or live behavior.
- Do not invent docs, coverage claims, flows, failures, or manual QA steps that are not grounded in checked evidence.
- Ask when a required behavior, source, credential, artifact, or proof target remains unclear after bounded inspection.

## Proof Selection

- Define the changed behavior boundary before choosing proof: local logic, process boundary, API or transport boundary, persistence, startup, CLI/app wiring, streaming, UI, release, or user workflow.
- Default to test-driven work for runtime behavior when feasible.
- Unit tests prove local logic. Keep them offline, deterministic, and based on realistic minimal objects.
- Integration or E2E tests prove behavior that crosses process, API, transport, persistence, startup, CLI/app wiring, streaming, workspace, or runtime boundaries.
- Unit tests are not acceptable proof for pure integration behavior.
- Pull-request checks and unit tests are useful evidence, but they do not replace end-user proof when the report came from a user-visible flow.
- When persisted state, queued work, history, SDK payloads, UI state, or similar internal state crosses a process, API, or transport boundary, prove both local behavior and the exact serialized outbound payload or boundary contract.
- For docs-only or formatting-only edits, use a formatter or linter instead of runtime tests.
- Do not continue if a required command fails.

## Bug Proof

- Reproduce the reported failure before fixing it.
- Add or extend an automated test that fails for the report before runtime code changes.
- Rerun the exact failed flow against the same kind of build or artifact and starting state before calling the bug fixed.
- UI and visual bugs need a real screenshot or rendered evidence from the installed or user-visible build; text-only dumps do not close visual bugs.
- CLI bugs need the exact command against the released build or a fresh install.
- Do not claim a fix is done, and do not close a requirement, until end-user proof exists and is cited.

## User Flow Coverage

- Read the relevant docs, examples, issue, pull request, or source sections when user-visible behavior, release QA, or a listed workflow is touched.
- Every documented user flow should have automated integration coverage or a documented manual QA path.
- Record docs or example coverage gaps in the checked-in owner for that flow when one exists.
- If a changed flow lacks integration coverage and no honest manual QA path can be documented inside the mandate, stop and escalate with the missing flow and why it cannot be proven.
- Keep Agency Swarm-specific coverage named and mapped to docs, examples, or source behavior when feasible so unrelated tests cannot hide regressions.

## Adjacent Agent Swarm TUI E2E

- For Agent Swarm terminal TUI behavior in the adjacent `agentswarm-cli` repo, use `.codex/skills/agent-swarm-tui-e2e` and the adjacent-fork mandate rules in `AGENTS.md`.
- Do not apply adjacent `agentswarm-cli` TUI harness commands to this repo unless the user explicitly expands the mandate to that repo or artifact.
- If a local Agency Swarm change affects the documented terminal TUI contract, prove the Agency Swarm side with Python tests or examples here and record any required adjacent TUI proof as a scoped blocker.

## Test Writing

- Keep each test function about 100 lines or less.
- Test behavior, not private implementation details, unless the private boundary is the only reliable proof target.
- Use real framework objects and the real implementation when practical.
- Avoid mocks unless they isolate an external dependency that is not the behavior under test.
- Do not copy production logic into tests.
- Prefer extending nearby tests over adding new test files unless nearby tests cannot cleanly cover the behavior.
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

- Use `uv` and repo `make` targets. Do not use global interpreters or absolute paths when repo tooling can run the check.
- For long-running commands, use timeouts that match the real wait window instead of stopping early.
- Run commands from the repo root through `make` or `uv run` unless a tool-specific package script is clearly the right scope.
- Run the smallest high-signal focused command first.
- For focused tests, run `uv run pytest <target>`.
- For runtime or behavior changes, run all related behavior you touched before commit, pull request, merge, release, or a done claim.
- Format touched Python files before each commit: `make format`.
- Type-check before staging or committing: `make check`.
- Run `make ci` before build-impact pull requests, merges, releases, or repo-wide health claims. Docs-only and policy-only changes use formatter and diff checks unless a live PR gate requires more.
- For docs changes that affect navigation or layout, run or request `make serve-docs` as appropriate for preview evidence.
- For provider-specific integrations or live services, run full related coverage when needed credentials exist; key-based skips are not proof.
- If planned validation needs a real LLM or live service, verify credentials and access before asking the user for keys or permission.

## Manual QA

- Use manual QA only when automation cannot honestly prove the user path within the mandate or when the release gate requires the user to test the local build.
- Write the manual QA target before running it: artifact, command, environment, starting state, expected visible result, and failure evidence to capture.
- Manual QA for UI or visual behavior must capture a screenshot or rendered evidence from the installed or user-visible build.
- Manual QA does not replace automated coverage when the behavior is stable enough to test.
- Record any manual gap in the checked-in owner for that flow, or escalate if no owner exists.

## Installed Package And Version Proof

- Before saying a local installed package or command is updated, verify from a fresh shell that the exact import or command the user will run resolves to the expected package path and version.
- Check all likely command names, Python imports, virtual environments, package-manager shims, shell hash tables, and cached installs when they can affect the user command.
- Prove that no package manager, cache, `PATH` entry, symlink, or wrapper returns an older published version.
- Record the resolved command path or import path, version output, package source when relevant, and the fresh-shell command used.
- If a wrapper or package manager still resolves to an older published version, do not claim the local install is updated; fix the install path or escalate with the exact stale resolver.

## Release Proof

- Before release approval, prove the exact release commit satisfies the live repo gates and relevant workflow runs for its ref, or their local equivalents when GitHub cannot run them.
- Required local release proof includes `make ci`, focused integration coverage, docs checks when docs changed, and repo-specific release or publish workflow requirements.
- Before any release or safety claim, build and install the fresh local package so the user's normal Agency Swarm import or command points to it.
- Verify installed package and version proof from a fresh shell before handing the build to the user.
- Run the exact affected Agency Swarm command, example, or import path and verify the expected user-visible behavior.
- Any launch, import, or command failure blocks release proof until the root cause is reproduced.
