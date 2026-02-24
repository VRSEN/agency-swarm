# v1.8.0 — Present and Accounted For

This release focuses on safer file presentation, stronger cross-provider history replay, richer metadata, and better first-turn UX via quick-reply caching.

## Breaking Changes

- Agent guardrail error flag migration:
  - Canonical flag is now `raise_input_guardrail_error`.
  - `throw_input_guardrail_error` is still accepted as a deprecated alias.
  - `return_input_guardrail_errors` is removed and now fails fast with migration guidance.
- Top-level handoff exports were clarified:
  - `Handoff` now points to the Agency Swarm handoff tool export.
  - OpenAI Agents SDK handoff is exported as `SDKHandoff`.

## Features

- Added built-in `PresentFiles` tool:
  - Moves files into the MNT area for UI presentation.
  - Supports overwrite controls and safe replacement.
  - Preserves symlinks safely and avoids data-loss edge cases.
- Added quick-reply support in starter cache flow:
  - `quick_replies` now participates in cache lookup/replay.
  - Cache fingerprinting now includes shared instructions and runtime context.
- Added tool input schema exposure in agency metadata/graph for function tools.
- Added automatic WebSearch source inclusion for agents using `WebSearchTool` (`web_search_call.action.sources`).
- Added `extract_web_search_sources()` utility for source URL extraction from run results.

## Fixes & Improvements

- Hardened message history protocol detection and compatibility checks.
- Added explicit mixed/incompatible protocol errors to prevent invalid replay.
- Improved replay ID handling for function-call items across LiteLLM/OpenAI Responses transitions.
- Tightened metadata schema handling and FastAPI metadata coverage.
- Updated FastAPI and web search examples for current patterns.
- Fixed LiteLLM integration test import shadowing by relocating test modules and using skip-safe optional imports.
- Fixed slow agent initialization coverage by aligning vector-store readiness mocks with current polling behavior.

## Docs

- Split and reorganized guardrails docs into dedicated pages.
- Refreshed onboarding/getting-started docs and starter template guidance.
- Clarified FastAPI persistence callback behavior and cache wording.

## Internal Quality Notes

- Added extensive tests for:
  - history protocol compatibility and replay behavior
  - starter-cache replay paths
  - metadata schema output
  - PresentFiles behavior and edge cases

## Full Changelog

- Compare: https://github.com/VRSEN/agency-swarm/compare/v1.7.0...v1.8.0
