---
name: release
description: Cut a release of agency-swarm. Use when bumping the version, tagging, writing release notes or publishing the package.
---

# Release

A release is a public action: the maintainer approves the version, the release notes and the publish step before any of them happen (AGENTS.md 2.2).

## Steps

1. Bump the version in `pyproject.toml`. Backward compatibility is not a goal by itself (AGENTS.md 2.1): a breaking change gets a bigger version bump and a clear entry in the release notes and `docs/migration/guide.mdx`, not a compatibility shim.
2. Run `make ci`. The final run has no skipped test: tests that need real API keys run with real keys. One skipped test blocks the release.
3. Run a real example agency from this repository end to end against the release commit: send a first message and watch a non-empty streamed response. A launch, credential, dependency or interface failure blocks the release until its root cause is known.
4. Get a review of the exact release commit (load the `review` skill). Fix findings and repeat steps 2 and 3 if code changed.
5. Write the release notes: every user-visible change since the previous release, in plain language, following `.cursor/rules/writing-docs.mdc`. Name each breaking change with what worked before and what changes now.
6. Draft the tag, the GitHub release and the package upload for the maintainer's approval, then publish.

Keep a bugfix release minimal: no policy edits and no tooling churn.

Deployed agencies rebuild from a push to GitHub. Ship their code through the local clone and a push; never edit code in a hosting platform's editor.
