from dotenv import load_dotenv

# Automatically load environment variables from .env when the package is imported
load_dotenv(override=True)

# Re-export common Agents SDK utilities for simpler imports in docs/examples
from agents import (  # noqa: E402
    AgentHooks,
    AgentOutputSchemaBase,
    AsyncComputer,
    Computer,
    DynamicPromptFunction,
    GenerateDynamicPromptData,
    GuardrailFunctionOutput,
    Handoff,
    InputGuardrailTripwireTriggered,
    Model,
    ModelSettings,
    OpenAIChatCompletionsModel,
    OutputGuardrailTripwireTriggered,
    RunContextWrapper,
    RunHooks,
    RunResult,
    RunResultStreaming,
    StopAtTools,
    ToolsToFinalOutputFunction,
    function_tool,
    input_guardrail,
    output_guardrail,
    set_tracing_disabled,
    trace,
)
from agents.extensions.models.litellm_model import LitellmModel  # noqa: E402
from agents.model_settings import Headers, MCPToolChoice, ToolChoice  # noqa: E402
from openai._types import Body, Query  # noqa: E402
from openai.types.responses import ResponseIncludable  # noqa: E402
from openai.types.shared import Reasoning  # noqa: E402

from .agency.core import Agency  # noqa: E402
from .agent.core import AgencyContext, Agent  # noqa: E402
from .context import MasterContext  # noqa: E402
from .hooks import PersistenceHooks  # noqa: E402
from .integrations.fastapi import run_fastapi  # noqa: E402
from .integrations.mcp_server import run_mcp  # noqa: E402
from .tools import (  # noqa: E402
    BaseTool,
    CodeInterpreter,
    CodeInterpreterContainer,
    CodeInterpreterContainerCodeInterpreterToolAuto,
    CodeInterpreterTool,
    ComputerTool,
    FileSearchTool,
    FunctionTool,
    FunctionToolResult,
    HostedMCPTool,
    ImageGeneration,
    ImageGenerationInputImageMask,
    ImageGenerationTool,
    LocalShellTool,
    Mcp,
    McpAllowedTools,
    McpRequireApproval,
    SendMessage,
    WebSearchTool,
)
from .utils.thread import ThreadManager  # noqa: E402

__all__ = [
    "Agent",
    "Agency",
    "AgencyContext",
    "BaseTool",
    "MasterContext",
    "ThreadManager",
    "PersistenceHooks",
    "SendMessage",
    "run_fastapi",
    "run_mcp",
    # Re-exports from Agents SDK
    "ModelSettings",
    "OpenAIChatCompletionsModel",
    "function_tool",
    "FunctionTool",
    "RunContextWrapper",
    "output_guardrail",
    "input_guardrail",
    "GuardrailFunctionOutput",
    "OutputGuardrailTripwireTriggered",
    "InputGuardrailTripwireTriggered",
    "HostedMCPTool",
    "trace",
    "Reasoning",
    "LitellmModel",
    "CodeInterpreterTool",
    "ComputerTool",
    "FileSearchTool",
    "ImageGenerationTool",
    "LocalShellTool",
    "WebSearchTool",
    "Model",
    "AgentHooks",
    "RunHooks",
    "RunResult",
    "RunResultStreaming",
    "set_tracing_disabled",
    "AgentOutputSchemaBase",
    "CodeInterpreter",
    "ImageGeneration",
    "Mcp",
    "CodeInterpreterContainer",
    "CodeInterpreterContainerCodeInterpreterToolAuto",
    "ImageGenerationInputImageMask",
    "Computer",
    "AsyncComputer",
    "McpAllowedTools",
    "McpRequireApproval",
    "DynamicPromptFunction",
    "GenerateDynamicPromptData",
    "Handoff",
    "FunctionToolResult",
    "StopAtTools",
    "ToolsToFinalOutputFunction",
    "Headers",
    "ToolChoice",
    "MCPToolChoice",
    "Query",
    "Body",
    "ResponseIncludable",
]
