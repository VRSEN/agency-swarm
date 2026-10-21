---
name: sdk-upgrade
description: Upgrade openai-agents, LiteLLM or a provider SDK. Use whenever a pin for one of those packages changes in pyproject.toml.
---

# Upgrade the OpenAI Agents SDK or a provider SDK

The SDK moves fast and our wrappers can silently fall behind it. A custom session layer once missed the SDK's compaction capability for months because nobody compared the changelog with the wrapper. This procedure prevents that.

## Steps

1. Bump the pin in `pyproject.toml` and update every affected lockfile in the same change. Check out `references/openai-agents-python` at the new tag (clone it there if missing).
2. Read the SDK changelog between the old and new tag.
3. List every wrapper that mirrors an SDK abstraction (session, history items, streaming events, model settings, tracing, guardrails, handoffs; each names its SDK class in its docstring per AGENTS.md 1.3). For each new SDK feature, decide: the wrapper now supports it, the wrapper is deleted in favor of the SDK (AGENTS.md 1.4), or the gap is listed in the pull request with a GitHub issue drafted for the maintainer.
4. Run `make ci`.
5. Add or update an end-to-end test that makes a tool call or a delegation and then sends that history back to the model in the next turn. This catches history-format changes that unit tests miss.
6. In the pull request, name the old and new versions and list each new SDK feature a wrapper does not yet support.
