from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
import uuid
from pathlib import Path

from agents import FunctionTool

from agency_swarm.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


def from_file(file_path: str | Path) -> list[type[BaseTool] | FunctionTool]:
    """Dynamically imports BaseTool classes or FunctionTool instances from the provided module path."""
    file = Path(file_path)
    tools: list[type[BaseTool] | FunctionTool] = []

    module_name = file.stem
    module = None
    try:
        spec = importlib.util.spec_from_file_location(module_name, file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"{module_name}_{uuid.uuid4().hex}"] = module
            spec.loader.exec_module(module)
        else:  # pragma: no cover - defensive logging
            logger.error("Unable to import tool module %s", file)
    except Exception as e:
        logger.error("Error importing tool module %s: %s", file, e)

    if not module:
        return tools

    base_tool = getattr(module, module_name, None)
    if inspect.isclass(base_tool) and issubclass(base_tool, BaseTool) and base_tool is not BaseTool:
        try:
            tools.append(base_tool)
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error("Error adapting tool %s: %s", module_name, e)

    for obj in module.__dict__.values():
        if isinstance(obj, FunctionTool):
            tools.append(obj)

    return tools
