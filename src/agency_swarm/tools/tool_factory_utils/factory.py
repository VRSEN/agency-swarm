from __future__ import annotations

from agents import FunctionTool

from agency_swarm.tools.base_tool import BaseTool

from . import base_tool_adapter, file_loader, langchain, mcp, openapi_exporter, openapi_importer


class ToolFactory:
    """
    Thin facade that delegates to focused helpers. Keeps the public API stable while the
    heavy implementations live in purpose-built modules to avoid monolithic files.
    """

    from_langchain_tools = staticmethod(langchain.from_langchain_tools)
    from_langchain_tool = staticmethod(langchain.from_langchain_tool)

    from_openai_schema = staticmethod(openapi_importer.from_openai_schema)
    from_openapi_schema = staticmethod(openapi_importer.from_openapi_schema)

    from_file = staticmethod(file_loader.from_file)
    get_openapi_schema = staticmethod(openapi_exporter.get_openapi_schema)

    adapt_base_tool = staticmethod(base_tool_adapter.adapt_base_tool)
    from_mcp = staticmethod(mcp.from_mcp)


__all__ = ["ToolFactory", "FunctionTool", "BaseTool"]
