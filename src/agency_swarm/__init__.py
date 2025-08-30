from dotenv import load_dotenv

# Automatically load environment variables from .env when the package is imported
load_dotenv(override=True)

# Re-export common Agents SDK utilities for simpler imports in docs/examples
from agents import (  # noqa: E402
    FunctionTool,
    GuardrailFunctionOutput,
    HostedMCPTool,
    InputGuardrailTripwireTriggered,
    ModelSettings,
    OpenAIChatCompletionsModel,
    OutputGuardrailTripwireTriggered,
    RunContextWrapper,
    function_tool,
    input_guardrail,
    output_guardrail,
    trace,
)

from .agency.core import Agency  # noqa: E402
from .agent.core import AgencyContext, Agent  # noqa: E402
from .context import MasterContext  # noqa: E402
from .hooks import PersistenceHooks  # noqa: E402
from .integrations.fastapi import run_fastapi  # noqa: E402
from .integrations.mcp_server import run_mcp  # noqa: E402
from .tools import BaseTool  # noqa: E402
from .tools.send_message import SendMessage  # noqa: E402
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
]
