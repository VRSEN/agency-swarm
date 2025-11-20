from agents import (
    CodeInterpreterTool,
    ComputerTool,
    FileSearchTool,
    FunctionTool,
    FunctionToolResult,
    HostedMCPTool,
    ImageGenerationTool,
    LocalShellTool,
    ToolOutputFileContent,
    ToolOutputFileContentDict,
    ToolOutputImage,
    ToolOutputImageDict,
    ToolOutputText,
    ToolOutputTextDict,
    WebSearchTool,
    function_tool,
)
from openai.types.responses.tool_param import (
    CodeInterpreter,
    CodeInterpreterContainer,
    CodeInterpreterContainerCodeInterpreterToolAuto,
    ImageGeneration,
    ImageGenerationInputImageMask,
    Mcp,
    McpAllowedTools,
    McpRequireApproval,
)

from .base_tool import BaseTool
from .built_in import LoadFileAttachment, PersistentShellTool
from .concurrency import ToolConcurrencyManager
from .send_message import SendMessage, SendMessageHandoff
from .tool_factory import ToolFactory
from .utils import (
    tool_output_file_from_file_id,
    tool_output_file_from_path,
    tool_output_file_from_url,
    tool_output_image_from_file_id,
    tool_output_image_from_path,
    validate_openapi_spec,
)

__all__ = [
    "BaseTool",
    "ToolFactory",
    "ToolConcurrencyManager",
    "SendMessage",
    "SendMessageHandoff",
    "validate_openapi_spec",
    "tool_output_image_from_path",
    "tool_output_image_from_file_id",
    "tool_output_file_from_path",
    "tool_output_file_from_url",
    "tool_output_file_from_file_id",
    # Re-exports from Agents SDK
    "CodeInterpreterTool",
    "ComputerTool",
    "FileSearchTool",
    "FunctionTool",
    "FunctionToolResult",
    "HostedMCPTool",
    "ImageGenerationTool",
    "LocalShellTool",
    "WebSearchTool",
    "function_tool",
    "ToolOutputText",
    "ToolOutputTextDict",
    "ToolOutputImage",
    "ToolOutputImageDict",
    "ToolOutputFileContent",
    "ToolOutputFileContentDict",
    # Built-in tools
    "LoadFileAttachment",
    "PersistentShellTool",
    "IPythonInterpreter",
    # Tool parameter types from OpenAI
    "CodeInterpreter",
    "CodeInterpreterContainer",
    "CodeInterpreterContainerCodeInterpreterToolAuto",
    "ImageGeneration",
    "ImageGenerationInputImageMask",
    "Mcp",
    "McpAllowedTools",
    "McpRequireApproval",
]


def __getattr__(name: str):
    """Lazy import for IPythonInterpreter to handle optional jupyter dependency."""
    if name == "IPythonInterpreter":
        from .built_in import IPythonInterpreter

        # Cache it in globals so subsequent access doesn't trigger __getattr__ again
        globals()[name] = IPythonInterpreter
        return IPythonInterpreter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
