# ✅ Unified Source Code Structure Checklist

## 1) Naming & Imports
- [x] Rename `tools/BaseTool.py` → `tools/base_tool.py`
- [x] Rename `tools/ToolFactory.py` → `tools/tool_factory.py`
- [x] Update all imports to reflect renamed files
- [x] Standardize logging: use `logging` from stdlib everywhere
- [x] Remove non-standard/internal logger imports

## 2) Side Effects & Globals
- [x] Remove `.env` loading from `agency_swarm/__init__.py`
- [ ] Provide explicit bootstrap/init utilities instead
- [x] Replace global `event_stream_merger` with injected/factory instance
- [x] Refactor `AguiAdapter` to use per-instance run state (no global mutable state)
- [x] Avoid client instantiation/logging config at import time

## 3) Consolidation
- [x] Centralize message sanitization/formatting in one shared module
- [x] Remove duplicates from `agent/messages.py` and `messages/message_formatter.py`
- [x] Move `streaming_utils.py` into `utils/` or dedicated `streaming/` subpackage
- [x] Relocate `agent_core.py` into `agent/core.py`
- [x] Move `thread.py` into `threads/` or `utils/threads.py`
- [x] Expand and organize `utils/` to host shared helpers

## 4) Decomposition
- [x] Split `agency.py` into smaller modules (core, setup, responses, completions, helpers, visualization)
- [x] Split `agent/execution.py` into validation, file handling, streaming, tool coordination
- [x] Split `agent/file_manager.py` into file I/O, attachment validation, vector-store logic
- [x] Split `tools/tool_factory.py` into adapters/builders/invokers with registry pattern
- [x] Convert procedural helpers (`register_subagent`, `add_tool`) into `Agent` methods or service classes
- [ ] Introduce dedicated services:
  - [ ] `ToolLoader`
  - [ ] `SubagentRegistry`
  - [ ] `FileAttachmentService`
  - [ ] `PersistenceManager`
  - [ ] `VisualizationService`
  - [ ] `ToolAdapterRegistry`

## 5) Hygiene
- [ ] Shorten long methods (<100 lines where feasible)
- [x] Add missing imports (e.g., `import inspect` in `mcp_server.py`)
- [ ] Standardize docstrings across public APIs
- [ ] Enforce type hints across all public classes/functions
- [ ] Centralize cross-cutting concerns (logging, tracing) via adapters/middleware
