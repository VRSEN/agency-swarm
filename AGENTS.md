AGENTS.md — Agency-Swarm Codebase Navigation

Purpose
-------
This guide explains the core structure and best practices for working on the Agency-Swarm codebase.
Read this before making changes or asking the AI to write code.

--------

:card_index_dividers: Project Structure
- `agency_swarm/agency/agency.py` -- orchestrates multiple agents and handles communication between them.
- `agency_swarm/agents/agent.py` -- core agent logic for tools and instructions.
- `agency_swarm/threads/thread.py` -- manages conversation state and thread isolation.
- `agency_swarm/messages/message_output.py` -- utilities for displaying messages in the terminal.
- `agency_swarm/integrations/fastapi.py` -- helpers for exposing agencies over FastAPI.
- `agency_swarm/tools/` -- built-in tools (e.g., `SendMessage`) and the `ToolFactory`.
- `agency_swarm/tools/mcp/` -- support for the Model Context Protocol (MCP) server.
- `tests/` -- unit tests and demos covering communication, tools, and MCP integrations.

See `README.md` for setup; examples are located in `tests/demos/`.

--------

:vertical_traffic_light: Critical Coding Rules
- Max 500 lines per file. Refactor when over.
- Max 100 lines per method/function. Most should be 10–40.
- Single Responsibility Principle: one job per class/function.
- No god objects. Break up huge classes.
- No deep nesting. Prefer flat, readable logic.
- Extract helpers for repeated/complex logic.
- Meaningful names for files, classes, and methods—describe intent, not just what.
- Docstrings required for public methods and classes.

--------

:hammer_and_wrench: Patterns & Conventions
- Composition > Inheritance where possible.
- All communication between agents uses `SendMessage`.

--------

:mag_right: Quick Reference
- Run tests: `cd tests && pytest -v` (see `.github/workflows/test.yml`).
- Lint: `pre-commit run --all-files`.
- For anything unclear: check this file first, then ask.

--------

Keep this file up to date. It’s the single source of truth for new contributors and AI agents working in the codebase.
