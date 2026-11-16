# Contributing to Agency Swarm

Thank you for helping improve Agency Swarm. This guide covers the local setup, the checks a
change must pass, and the two maintainer procedures: an SDK upgrade and a release.

The rules every change follows are in [AGENTS.md](AGENTS.md). The most important one: Agency
Swarm is an orchestration layer over the
[OpenAI Agents SDK](https://github.com/openai/openai-agents-python). Where the SDK already does
something, use the SDK.

## Set up

You need Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/VRSEN/agency-swarm.git
cd agency-swarm
make sync                    # creates .venv and installs the dependencies
uv run pre-commit install    # runs the formatters on each commit
```

## Where things live

| Path | What it holds |
| --- | --- |
| `src/agency_swarm/` | The framework |
| `tests/test_*_modules/` | Unit tests, mirroring the source layout |
| `tests/integration/` | Integration tests |
| `examples/` | Runnable examples |
| `docs/` | The documentation site at [agency-swarm.ai](https://agency-swarm.ai) |

## Make a change

1. Create a branch from `main`.
2. Write the change. A change to existing behavior comes with a test that fails without it.
3. Run the checks:

   ```bash
   make format     # ruff format and autofix
   make check      # ruff and mypy
   make tests      # the test suite
   make coverage   # the test suite with coverage; fails below 90%
   ```

   `make ci` runs all of them in one go. Use it before a broad or risky change.
4. Update the docs when behavior that users see changes. `make serve-docs` previews the site
   locally with the Mintlify CLI.
5. Open a pull request and fill in the template: what changed, why, and how you tested it.

The integration tests call OpenAI and need `OPENAI_API_KEY` in your environment. The unit
tests run without a key: `uv run pytest tests/test_*_modules`.

## Upgrade the OpenAI Agents SDK

Use this procedure when the pin for `openai-agents`, LiteLLM or a provider SDK changes.

1. Change the pin in `pyproject.toml` and update `uv.lock` in the same change.
2. Read the SDK changelog between the old and the new version.
3. List every wrapper in `src/` that mirrors an SDK abstraction: session, history items,
   streaming events, model settings, tracing, guardrails, handoffs. For each new SDK feature,
   choose one: the wrapper supports it, the wrapper is deleted in favor of the SDK, or the gap
   is named in the pull request.
4. Run `make ci`.
5. Add or update an end-to-end test that makes a tool call or a delegation and then sends that
   history back to the model on the next turn. This catches history-format changes that unit
   tests miss.
6. In the pull request, name the old and the new version and each SDK feature a wrapper does
   not support yet.

## Release

Maintainers cut releases.

1. Bump `version` in `pyproject.toml`. A breaking change gets an entry in the release notes and
   in `docs/migration/guide.mdx`.
2. Run `make ci`.
3. Run the **Live OpenAI Tests** workflow on the release commit. It also runs the tests that the
   regular CI skips. A failing test blocks the release.
4. Run one example from `examples/` end to end against the release commit: send a first message
   and watch a streamed response arrive.
5. Write the release notes: every change a user can see since the previous release, in plain
   language. For each breaking change, say what worked before and what changes now.
6. Publish the GitHub release. The **Publish to PyPI** workflow uploads the package.
