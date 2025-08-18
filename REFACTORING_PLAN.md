# ✅ Unified Source Code Structure Checklist

## 1) Naming & Imports
- [x] Rename `tools/BaseTool.py` → `tools/base_tool.py`
- [x] Rename `tools/ToolFactory.py` → `tools/tool_factory.py`
- [x] Update all imports to reflect renamed files
- [ ] Standardize logging: use `logging` from stdlib everywhere
- [ ] Remove non-standard/internal logger imports

## 2) Side Effects & Globals
- [ ] Remove `.env` loading from `agency_swarm/__init__.py`
- [ ] Provide explicit bootstrap/init utilities instead
- [ ] Replace global `event_stream_merger` with injected/factory instance
- [ ] Refactor `AguiAdapter` to use per-instance run state (no global mutable state)
- [ ] Avoid client instantiation/logging config at import time

## 3) Consolidation
- [ ] Centralize message sanitization/formatting in one shared module
- [ ] Remove duplicates from `agent/messages.py` and `messages/message_formatter.py`
- [x] Move `streaming_utils.py` into `utils/` or dedicated `streaming/` subpackage
- [ ] Relocate `agent_core.py` into `agent/core.py`
- [ ] Move `thread.py` into `threads/` or `utils/threads.py`
- [ ] Expand and organize `utils/` to host shared helpers

## 4) Decomposition
- [ ] Split `agency.py` into smaller modules (init, persistence, streaming, deprecated APIs)
- [ ] Split `agent/execution.py` into validation, file handling, streaming, tool coordination
- [ ] Split `agent/file_manager.py` into file I/O, attachment validation, vector-store logic
- [ ] Split `tools/tool_factory.py` into adapters/builders/invokers with registry pattern
- [ ] Convert procedural helpers (`register_subagent`, `add_tool`) into `Agent` methods or service classes
- [ ] Introduce dedicated services:
  - [ ] `ToolLoader`
  - [ ] `SubagentRegistry`
  - [ ] `FileAttachmentService`
  - [ ] `PersistenceManager`
  - [ ] `VisualizationService`
  - [ ] `ToolAdapterRegistry`

## 5) Boundaries
- [ ] Reorganize `integrations/` into `integrations/fastapi/` and `integrations/mcp/`
- [ ] Define stable interfaces/registries for integrations
- [ ] Move demo launchers out of `ui/` into `examples/` or `demos/`
- [ ] Keep `ui/` focused only on reusable adapters/components

## 6) Hygiene
- [ ] Shorten long methods (<100 lines where feasible)
- [ ] Add missing imports (e.g., `import inspect` in `mcp_server.py`)
- [ ] Standardize docstrings across public APIs
- [ ] Enforce type hints across all public classes/functions
- [ ] Centralize cross-cutting concerns (logging, tracing) via adapters/middleware
