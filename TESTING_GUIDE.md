# Testing Guide (Minimal, Deterministic, Human-Readable)

## Principles
- Prefer tiny, deterministic tests with hardcoded inputs/outputs.
- Avoid model-driven or network tests unless explicitly needed.
- Prove a failure first (TDD), then implement the fix.

## Patterns To Follow
- For ordering: instantiate `ThreadManager`, add dict records with explicit `timestamp`, assert final order by `type` or `content`.
- For tools: call the function directly with minimal args; assert exact return value.
- For streaming: when unavoidable, compare only essential fields and limit to 3–5 events.

## Example (Message Order)
1) Create a few message dicts with `timestamp` 1000, 1001, 1002.
2) Append to `ThreadManager`.
3) Slice new messages and assert `['message', 'function_call', 'function_call_output']`.

## DO NOT
- Do not write tests that depend on full agent execution for basic invariants.
- Do not write tests that are hard to read or reason about.
