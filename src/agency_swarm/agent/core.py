import inspect
import logging
import os
import warnings
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, TypeVar

from agents import Agent as BaseAgent, RunConfig, RunHooks, RunResult, Tool, TResponseInputItem
from openai import AsyncOpenAI, OpenAI

from agency_swarm.agent import (
    Execution,
    add_tool,
    handle_deprecated_parameters,
    load_tools_from_folder,
    parse_schemas,
    separate_kwargs,
    setup_file_manager,
    validate_hosted_tools,
    wrap_input_guardrails,
)
from agency_swarm.agent.agent_flow import AgentFlow
from agency_swarm.agent.attachment_manager import AttachmentManager
from agency_swarm.agent.file_manager import AgentFileManager
from agency_swarm.agent.tools import _attach_one_call_guard
from agency_swarm.context import MasterContext
from agency_swarm.tools.concurrency import ToolConcurrencyManager
from agency_swarm.tools.mcp_manager import register_and_connect_agent_servers

from .context_types import AgencyContext as AgencyContext

logger = logging.getLogger(__name__)

"""Constants moved to agency_swarm.agent.constants (no behavior change)."""

T = TypeVar("T", bound="Agent")


"""AgencyContext moved to agency_swarm.agent.context_types (no behavior change)."""


class Agent(BaseAgent[MasterContext]):
    """
    Agency Swarm Agent: Extends the base `agents.Agent` with capabilities for
    multi-agent collaboration within an `Agency`.

    This class manages agent-specific parameters like file folders, response validation,
    and handles the registration of subagents to enable communication within the agency
    structure defined by an `AgencyChart`. It relies on the underlying `agents` SDK
    for core execution logic via the `Runner`.

    Agents are stateless. Agency-specific resources like thread managers,
    subagent mappings and shared instructions are provided at runtime via
    :class:`AgencyContext` from the owning :class:`Agency`.
    """

    # --- Agency Swarm Specific Parameters ---
    files_folder: str | Path | None
    tools_folder: str | Path | None  # Directory path for automatic tool discovery and loading
    description: str | None
    output_type: type[Any] | None
    send_message_tool_class: type | None  # Custom SendMessage tool class for inter-agent communication
    include_search_results: bool = False
    validation_attempts: int = 1
    throw_input_guardrail_error: bool = False

    # --- Internal State ---
    _associated_vector_store_id: str | None = None
    files_folder_path: Path | None = None
    _openai_client: AsyncOpenAI | None = None
    _openai_client_sync: OpenAI | None = None
    file_manager: AgentFileManager | None = None  # Initialized in setup_file_manager()
    attachment_manager: AttachmentManager | None = None  # Initialized in setup_file_manager()
    _tool_concurrency_manager: ToolConcurrencyManager
    _subagents: dict[str, "Agent"] | None = None  # Other agents that this agent can communicate with

    # --- SDK Agent Compatibility ---
    # Re-declare attributes from BaseAgent for clarity and potential overrides

    def __init__(self, **kwargs: Any):
        """
        Initializes the Agency Swarm Agent.

        ## Agency Swarm-Specific Parameters:
            name (str): The name of the agent. **Required**.
            instructions (str | Path | None): System prompt for the agent. Can be provided as a string or a file path.
            description (str | None): Agent role description for dynamic send_message and handoff tool generation.
            files_folder (str | Path | None): Path to agent's file directory. If named `*_vs_<vector_store_id>`,
                files are automatically added to the specified OpenAI Vector Store and FileSearchTool is added.
            tools_folder (str | Path | None): Directory for automatic tool discovery and loading.
            schemas_folder (str | Path | None): Directory containing OpenAPI schema files
                for automatic tool generation.
            api_headers (dict[str, dict[str, str]] | None): Per-schema headers for OpenAPI tools. Format:
                {"schema_filename.json": {"header_name": "header_value"}}.
            api_params (dict[str, dict[str, Any]] | None): Per-schema parameters for OpenAPI tools. Format:
                {"schema_filename.json": {"param_name": "param_value"}}.
            send_message_tool_class (type | None): Custom SendMessage tool class for inter-agent communication.
                Note: This parameter can be used to define handoffs by using SendMessageHandoff here.
            include_search_results (bool): Include search results in FileSearchTool output for citation extraction.
                Defaults to False.
            validation_attempts (int): Number of retries when an output guardrail trips. Defaults to 1.
            throw_input_guardrail_error (bool): Whether to raise input guardrail errors as exceptions.
                Defaults to False.

        ## OpenAI Agents SDK Parameters:
            prompt (Prompt | DynamicPromptFunction | None): Dynamic prompt configuration.
            model (str | Model | None): Model identifier (e.g., "gpt-5") or Model instance.
                If not provided, the agents SDK default model will be used: https://openai.github.io/openai-agents-python/models
            model_settings (ModelSettings | None): Model configuration (temperature, max_tokens, etc.).
            tools (list[Tool] | None): Tool instances for the agent. Defaults to empty list.
            mcp_servers (list[MCPServer] | None): Model Context Protocol servers.
            mcp_config (MCPConfig | None): MCP server configuration.
            input_guardrails (list[InputGuardrail] | None): Pre-execution validation checks.
            output_guardrails (list[OutputGuardrail] | None): Post-execution validation checks.
            output_type (type[Any] | AgentOutputSchemaBase | None): Type of agent's final output.
            hooks (AgentHooks | None): Lifecycle event callbacks.
            tool_use_behavior ("run_llm_again" | "stop_on_first_tool" | list[str] | Callable): Tool usage behavior.
                How tool usage is handled:
                • "run_llm_again": The default behavior. Tools are run, and then the LLM receives the results
                    and gets to respond.
                • "stop_on_first_tool": The output of the first tool call is used as the final output. This
                    means that the LLM does not process the result of the tool call.
                • A list of tool names: The agent will stop running if any of the tools in the list are called.
                    The final output will be the output of the first matching tool call. The LLM does not
                    process the result of the tool call.
                • A function: If you pass a function, it will be called with the run context and the list of
                    tool results. It must return a `ToolToFinalOutputResult`, which determines whether the tool
                    calls result in a final output.
            reset_tool_choice (bool | None): Whether to reset tool choice after tool calls.
        """
        # Handle deprecated parameters
        handle_deprecated_parameters(kwargs)

        # examples are appended to instructions
        if "examples" in kwargs:
            examples = kwargs.pop("examples")
            if examples and isinstance(examples, list):
                try:
                    import json as _json

                    examples_str = "\n\nExamples:\n" + "\n".join(f"- {_json.dumps(ex)}" for ex in examples)
                    current_instructions = kwargs.get("instructions", "")
                    kwargs["instructions"] = current_instructions + examples_str
                except Exception:
                    logger.exception("Failed to append examples to instructions")

        # Separate kwargs into base agent params and agency swarm params
        base_agent_params, current_agent_params = separate_kwargs(kwargs)

        # Validate required parameters
        if "name" not in base_agent_params:
            raise ValueError("Agent requires a 'name' parameter.")
        if "tools" not in base_agent_params:
            base_agent_params["tools"] = []
        elif not isinstance(base_agent_params["tools"], list):
            raise TypeError("'tools' parameter must be a list.")

        if "tools" in kwargs:
            tools_list = kwargs["tools"]
            # Validate that hosted tools are properly initialized
            validate_hosted_tools(tools_list)

        # Remove description from base_agent_params if it was added for Swarm Agent
        base_agent_params.pop("description", None)

        # Initialize base agent
        super().__init__(**base_agent_params)

        # Initialize Agency Swarm specific attributes
        self.files_folder = current_agent_params.get("files_folder")
        self.tools_folder = current_agent_params.get("tools_folder")
        self.schemas_folder = current_agent_params.get("schemas_folder")
        self.api_headers = current_agent_params.get("api_headers", {})
        self.api_params = current_agent_params.get("api_params", {})
        self.description = current_agent_params.get("description")
        self.send_message_tool_class = current_agent_params.get("send_message_tool_class")
        self.include_search_results = current_agent_params.get("include_search_results", False)
        self.validation_attempts = int(current_agent_params.get("validation_attempts", 1))
        self.throw_input_guardrail_error = bool(current_agent_params.get("throw_input_guardrail_error", False))

        # Internal state
        self._openai_client = None
        self._openai_client_sync = None
        self._tool_concurrency_manager = ToolConcurrencyManager()

        # Initialize execution handler
        self._execution = Execution(self)

        # Set files_folder_path
        if self.files_folder:
            files_folder_path = Path(self.files_folder)
            if files_folder_path.is_absolute():
                self.files_folder_path = files_folder_path.resolve()
            else:
                self.files_folder_path = (Path(self.get_class_folder_path()) / files_folder_path).resolve()
        else:
            self.files_folder_path = None

        # Set up file manager and tools
        setup_file_manager(self)
        # file_manager is always initialized by setup_file_manager()
        if self.file_manager is None:
            raise RuntimeError(f"Agent {self.name} has no file manager configured")

        self.file_manager.read_instructions()
        self.file_manager._parse_files_folder_for_vs_id()
        parse_schemas(self)
        load_tools_from_folder(self)

        # Wrap input guardrails
        wrap_input_guardrails(self)

        # Wrap any FunctionTool instances that were provided directly via constructor
        for tool in self.tools:
            _attach_one_call_guard(tool, self)

        # Register and connect MCP servers by default (persistent across runs)
        register_and_connect_agent_servers(self)

    # --- Deprecated Compatibility ---
    @property
    def return_input_guardrail_errors(self) -> bool:  # pragma: no cover - deprecated
        warnings.warn(
            "'return_input_guardrail_errors' is deprecated; use 'throw_input_guardrail_error'",
            DeprecationWarning,
            stacklevel=2,
        )
        return not self.throw_input_guardrail_error

    @return_input_guardrail_errors.setter
    def return_input_guardrail_errors(self, value: bool) -> None:  # pragma: no cover - deprecated
        warnings.warn(
            "'return_input_guardrail_errors' is deprecated; use 'throw_input_guardrail_error'",
            DeprecationWarning,
            stacklevel=2,
        )
        self.throw_input_guardrail_error = not value

    # --- Properties ---
    def __repr__(self) -> str:
        """Return a string representation of the Agent instance."""
        # Get model information - try model_settings.model first, then fall back to model attribute
        model_info = "unknown"
        if hasattr(self, "model_settings") and self.model_settings and hasattr(self.model_settings, "model"):
            model_info = self.model_settings.model
        elif hasattr(self, "model") and self.model:
            model_info = str(self.model)

        return f"<Agent name={self.name!r} desc={self.description!r} model={model_info!r}>"

    @property
    def client(self) -> AsyncOpenAI:
        """Provides access to an initialized AsyncOpenAI client instance."""
        if not hasattr(self, "_openai_client") or self._openai_client is None:
            self._openai_client = AsyncOpenAI()
        return self._openai_client

    @property
    def client_sync(self) -> OpenAI:
        """Provides access to an initialized sync OpenAI client instance."""
        if not hasattr(self, "_openai_client_sync") or self._openai_client_sync is None:
            self._openai_client_sync = OpenAI()
        return self._openai_client_sync

    @property
    def tool_concurrency_manager(self) -> ToolConcurrencyManager:
        """Provides access to the agent's tool concurrency manager."""
        return self._tool_concurrency_manager

    # --- Tool Management ---
    def add_tool(self, tool: Tool) -> None:
        """
        Adds a `Tool` instance to the agent's list of tools.

        Ensures the tool is a valid `agents.Tool` instance and prevents adding
        tools with duplicate names.

        Args:
            tool (Tool): The `agents.Tool` instance to add.

        Raises:
            TypeError: If the provided `tool` is not an instance of `agents.Tool`.
        """
        add_tool(self, tool)

    def _load_tools_from_folder(self) -> None:
        """Load tools defined in ``tools_folder`` and add them to the agent.

        Supports both ``BaseTool`` subclasses and ``FunctionTool``
        instances created via the ``@function_tool`` decorator.
        """
        load_tools_from_folder(self)

    def _parse_schemas(self):
        """Parse OpenAPI schemas from the schemas folder and create tools."""
        parse_schemas(self)

    # --- File Handling ---
    def upload_file(self, file_path: str, include_in_vector_store: bool = True) -> str:
        """Upload a file using the agent's file manager."""
        if self.file_manager:
            return self.file_manager.upload_file(file_path, include_in_vector_store)
        raise RuntimeError(f"Agent {self.name} has no file manager configured")

        # --- Core Execution Methods ---

    async def get_response(
        self,
        message: str | list[TResponseInputItem],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        message_files: list[str] | None = None,  # Backward compatibility
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        agency_context: AgencyContext | None = None,  # Context from agency, or None for standalone
        **kwargs: Any,
    ) -> RunResult:
        """
        Runs the agent's turn in the conversation loop, handling both user and agent-to-agent interactions.

        This method serves as the primary interface for interacting with the agent. It processes
        the input message, manages conversation history via threads, runs the agent using the
        `agents.Runner`, validates responses, and persists the results.

        Args:
            message: The input message as a string or structured input items list
            sender_name: Name of the sending agent (None for user interactions)
            context_override: Optional context data to override default MasterContext values
            hooks_override: Optional hooks to override default agent hooks
            run_config_override: Optional run configuration settings
            message_files: DEPRECATED: Use file_ids instead. File IDs to attach to the message
            file_ids: List of OpenAI file IDs to attach to the message
            additional_instructions: Additional instructions to be appended to the agent's
                                    instructions for this run only
            agency_context: AgencyContext for this execution (provided by Agency, or None for standalone use)
            **kwargs: Additional keyword arguments including max_turns

        Returns:
            RunResult: The complete execution result
        """
        # If no agency context provided, create a minimal one for standalone usage
        if agency_context is None:
            agency_context = self._create_minimal_context()

        return await self._execution.get_response(
            message=message,
            sender_name=sender_name,
            context_override=context_override,
            hooks_override=hooks_override,
            run_config_override=run_config_override,
            message_files=message_files,
            file_ids=file_ids,
            additional_instructions=additional_instructions,
            agency_context=agency_context,
            **kwargs,
        )

    async def get_response_stream(
        self,
        message: str | list[TResponseInputItem],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        message_files: list[str] | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        agency_context: AgencyContext | None = None,  # Context from agency, or None for standalone
        **kwargs,
    ) -> AsyncGenerator[Any]:
        """Runs the agent's turn in streaming mode.

        Args:
            message: The input message or list of message items
            sender_name: Name of the sending agent (None for user interactions)
            context_override: Optional context data to override default values
            hooks_override: Optional hooks to override default agent hooks
            run_config_override: Optional run configuration
            additional_instructions: Additional instructions to be appended to the agent's
                                    instructions for this run only
            message_files: DEPRECATED: Use file_ids instead. File IDs to attach to the message
            file_ids: List of OpenAI file IDs to attach to the message
            agency_context: AgencyContext for this execution (provided by Agency, or None for standalone use)
            **kwargs: Additional keyword arguments

        Yields:
            Stream events from the agent's execution
        """
        # If no agency context provided, create a minimal one for standalone usage
        if agency_context is None:
            agency_context = self._create_minimal_context()

        async for event in self._execution.get_response_stream(
            message=message,
            sender_name=sender_name,
            context_override=context_override,
            hooks_override=hooks_override,
            run_config_override=run_config_override,
            message_files=message_files,
            file_ids=file_ids,
            additional_instructions=additional_instructions,
            agency_context=agency_context,
            **kwargs,
        ):
            yield event

    # --- Helper Methods ---
    # _validate_response removed - use output_guardrails instead

    def _create_minimal_context(self) -> AgencyContext:
        """Create a minimal context for standalone agent usage (no agency)."""
        from ..utils.thread import ThreadManager

        return AgencyContext(
            agency_instance=None,
            thread_manager=ThreadManager(),
            subagents={},
            load_threads_callback=None,
            save_threads_callback=None,
            shared_instructions=None,
        )

    def __gt__(self, other: "Agent") -> "AgentFlow":
        """
        Allow creating agent flows with > operator.

        Usage: agent1 > agent2 > agent3 > agent4 creates complete chain
        """
        if not isinstance(other, Agent):
            raise TypeError("Can only chain to Agent instances")
        return AgentFlow([self, other])

    def __lt__(self, other: "Agent") -> "AgentFlow":
        """
        Allow creating agent flows with < operator.

        Usage: agent1 < agent2 creates a flow from agent2 to agent1 (reversed)
        """
        if not isinstance(other, Agent):
            raise TypeError("Can only chain to Agent instances")
        return AgentFlow([other, self])

    def register_subagent(self, recipient_agent: "Agent", send_message_tool_class: type | None = None) -> None:
        """
        Registers another agent as a subagent that this agent can communicate with.

        This method delegates to the standalone register_subagent function for tool creation.

        Args:
            recipient_agent (Agent): The `Agent` instance to register as a recipient.
            send_message_tool_class: Optional custom send message tool class to use for this specific
                               agent-to-agent communication. If None, uses agent's default or SendMessage.
        """
        # Import to avoid circular dependency
        from .subagents import register_subagent as register_subagent_func

        # Use the existing register_subagent function for tool creation
        register_subagent_func(self, recipient_agent, send_message_tool_class)

    def _get_caller_directory(self) -> str:
        """Get the directory where this agent is being instantiated (caller's directory)."""
        try:
            # Get the agency_swarm package path for comparison (we're already in it)
            agency_swarm_path = os.path.dirname(os.path.abspath(__file__))

            # Walk up the call stack to find the first frame outside of agency_swarm package
            frame = inspect.currentframe()
            while frame is not None:
                frame_module = inspect.getmodule(frame)
                if frame_module and hasattr(frame_module, "__file__") and frame_module.__file__:
                    module_path = os.path.dirname(os.path.abspath(frame_module.__file__))
                    # Check if module is outside the agency_swarm package directory
                    if not module_path.startswith(agency_swarm_path):
                        return os.path.dirname(os.path.abspath(frame.f_code.co_filename))
                frame = frame.f_back
        except Exception:
            pass
        finally:
            # Prevent reference cycles
            del frame

        # Fall back to current working directory
        return os.getcwd()

    def get_class_folder_path(self) -> str:
        """Return the absolute path to the folder where this agent was instantiated."""
        # For relative path resolution, use caller directory instead of class location
        return self._get_caller_directory()
