from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
import uuid
from pathlib import Path
from types import ModuleType

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
        # Use a stable namespace per tools folder so shared helpers are imported once.
        package_name = _stable_package_name(file.parent)
        full_module_name = f"{package_name}.{module_name}"

        package_module = _get_or_create_namespace_package(package_name, file.parent)
        sys.modules.setdefault(package_name, package_module)

        spec = importlib.util.spec_from_file_location(full_module_name, file)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            module.__package__ = package_name
            sys.modules[full_module_name] = module
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


_namespace_cache: dict[Path, str] = {}


def _stable_package_name(folder: Path) -> str:
    """Derive a stable namespace package name per tools folder."""
    folder = folder.resolve()
    if folder in _namespace_cache:
        return _namespace_cache[folder]
    # Use a UUID5 based on the absolute folder path to keep it deterministic.
    # Use hex to avoid hyphens, keeping the package name identifier-safe.
    uid_hex = uuid.uuid5(uuid.NAMESPACE_URL, str(folder)).hex
    namespace = f"_agency_swarm_tools_{uid_hex}"
    _namespace_cache[folder] = namespace
    return namespace


def _get_or_create_namespace_package(package_name: str, folder: Path) -> ModuleType:
    """Create or reuse a namespace package for a tools folder."""
    existing = sys.modules.get(package_name)
    if isinstance(existing, ModuleType):
        return existing

    package_module = ModuleType(package_name)
    package_spec = importlib.util.spec_from_loader(package_name, loader=None, is_package=True)
    if package_spec:
        package_spec.submodule_search_locations = [str(folder)]
        package_module.__spec__ = package_spec
        package_module.__path__ = package_spec.submodule_search_locations
    else:
        package_module.__path__ = [str(folder)]
    package_module.__package__ = package_name
    return package_module
