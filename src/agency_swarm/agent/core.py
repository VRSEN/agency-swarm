import json
import logging
import os
import warnings
from pathlib import Path
from typing import Any, TypeVar

from agents import (
    Agent as BaseAgent,
    RunConfig,
    RunContextWrapper,
    RunHooks,
    RunResult,
    Tool,
    TResponseInputItem,
)
from openai import AsyncOpenAI, OpenAI

from agency_swarm.agent import (
    Execution,
    add_tool,
    apply_framework_defaults,
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
from agency_swarm.agent.execution_streaming import StreamingRunResponse
from agency_swarm.agent.file_manager import AgentFileManager
from agency_swarm.agent.tools import _attach_one_call_guard
from agency_swarm.context import MasterContext
from agency_swarm.tools.concurrency import ToolConcurrencyManager
from agency_swarm.tools.mcp_manager import convert_mcp_servers_to_tools

from .context_types import AgencyContext as AgencyContext, AgentRuntimeState

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
    send_message_tool_class: type | None  # DEPRECATED: configure SendMessage tools via communication_flows
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
            send_message_tool_class (type | None): DEPRECATED. Configure SendMessage tool classes via
                `communication_flows` on `Agency` instead of setting this per agent.
            include_search_results (bool): Include search results in FileSearchTool output for citation extraction.
                Defaults to False.
            validation_attempts (int): Number of retries when an output guardrail trips. Defaults to 1.
            throw_input_guardrail_error (bool): Whether to raise input guardrail errors as exceptions.
                Defaults to False.
            handoff_reminder (str | None): Custom reminder for handoffs.
                Defaults to `Transfer completed. You are {recipient_agent_name}. Please continue the task.`

        ## OpenAI Agents SDK Parameters:
            prompt (Prompt | DynamicPromptFunction | None): Dynamic prompt configuration.
            model (str | Model | None): Model identifier (e.g., "gpt-5.2") or Model instance.
                If not provided, the agents SDK default model will be used: https://openai.github.io/openai-agents-python/models
            model_settings (ModelSettings | None): Model configuration (temperature, max_tokens, etc.).
            tools (list[Tool] | None): Tool instances for the agent. Defaults to empty list.
            mcp_servers (list[MCPServer] | None): Model Context Protocol servers.
            mcp_config (MCPConfig | None): MCP server configuration.
            input_guardrails (list[InputGuardrail] | None): Pre-execution validation checks.
            output_guardrails (list[OutputGuardrail] | None): Post-execution validation checks.
            output_type (type[Any] | AgentOutputSchemaBase | None): Type of agent's final output.
            hooks (AgentHooks | None): Lifecycle event callbacks.
            tool_use_behavior ("run_llm_again" | "stop_on_first_tool" | StopAtTools | dict[str, Any] | Callable):
                Tool usage behavior.
                How tool usage is handled:
                • "run_llm_again": The default behavior. Tools are run, and then the LLM receives the results
                    and gets to respond.
                • "stop_on_first_tool": The output of the first tool call is used as the final output. This
                    means that the LLM does not process the result of the tool call.
                • A StopAtTools config (or compatible dict with ``stop_at_tool_names``) identifies tool names
                    that should terminate the run. The final output will be the output of the first matching
                    tool call. The LLM does not process the result of the tool call.
                • A function: If you pass a function, it will be called with the run context and the list of
                    tool results. It must return a `ToolsToFinalOutputResult`, which determines whether the tool
                    calls result in a final output.
            reset_tool_choice (bool | None): Whether to reset tool choice after tool calls.
        """
        # Handle deprecated parameters
        handle_deprecated_parameters(kwargs)

        # Apply framework defaults (e.g., truncation="auto")
        apply_framework_defaults(kwargs)

        # examples are appended to instructions
        if "examples" in kwargs:
            examples = kwargs.pop("examples")
            if examples and isinstance(examples, list):
                try:
                    examples_str = "\n\nExamples:\n" + "\n".join(f"- {json.dumps(ex)}" for ex in examples)
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
        self.handoff_reminder = current_agent_params.get("handoff_reminder")

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
        # Skip side-effectful OpenAI file/vector-store setup when DRY_RUN is enabled
        _dry_run_env = os.getenv("DRY_RUN", "")
        _DRY_RUN = str(_dry_run_env).strip().lower() in {"1", "true", "yes", "on"}
        if not _DRY_RUN:
            self.file_manager.parse_files_folder_for_vs_id()
        parse_schemas(self)
        load_tools_from_folder(self)

        # Wrap input guardrails
        wrap_input_guardrails(self)

        # Wrap any FunctionTool instances that were provided directly via constructor
        for tool in self.tools:
            _attach_one_call_guard(tool, self)

        # Convert MCP servers to tools and add them to the agent
        convert_mcp_servers_to_tools(self)

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

    async def get_all_tools(self, run_context: RunContextWrapper[MasterContext]) -> list[Tool]:
        """Include agency-scoped runtime tools alongside static tools."""
        base_tools = await super().get_all_tools(run_context)

        master_context = getattr(run_context, "context", None)
        runtime_tools: list[Tool] = []
        if master_context and getattr(master_context, "agent_runtime_state", None):
            runtime_state = master_context.agent_runtime_state.get(self.name)
            if runtime_state:
                runtime_tools = list(runtime_state.send_message_tools.values())

        if not runtime_tools:
            return base_tools

        seen = {id(tool) for tool in base_tools}
        for tool in runtime_tools:
            if id(tool) not in seen:
                base_tools.append(tool)
        return base_tools

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

    def get_response_stream(
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
        **kwargs: Any,
    ) -> StreamingRunResponse:
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

        Returns:
            StreamingRunResponse: Async iterable for stream events with access to the
            final streaming result.
        """
        # If no agency context provided, create a minimal one for standalone usage
        if agency_context is None:
            agency_context = self._create_minimal_context()

        return self._execution.get_response_stream(
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

    # --- Helper Methods ---
    # _validate_response removed - use output_guardrails instead

    def _create_minimal_context(self) -> AgencyContext:
        """Create a minimal context for standalone agent usage (no agency)."""
        from ..utils.thread import ThreadManager

        thread_manager = ThreadManager()
        runtime_state = AgentRuntimeState(self._tool_concurrency_manager)
        return AgencyContext(
            agency_instance=None,
            thread_manager=thread_manager,
            runtime_state=runtime_state,
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

    def register_subagent(
        self,
        recipient_agent: "Agent",
        send_message_tool_class: type | None = None,
        runtime_state: AgentRuntimeState | None = None,
    ) -> None:
        """
        Registers another agent as a subagent that this agent can communicate with.

        This method delegates to the standalone register_subagent function for tool creation.

        Args:
            recipient_agent (Agent): The `Agent` instance to register as a recipient.
            send_message_tool_class: Optional custom SendMessage tool for this specific communication.
                               Deprecated—prefer assigning tool classes via `communication_flows`.
            runtime_state: Optional runtime state container injected by the owning Agency
        """
        # Import to avoid circular dependency
        from .subagents import register_subagent as register_subagent_func

        # Use the existing register_subagent function for tool creation
        register_subagent_func(self, recipient_agent, send_message_tool_class, runtime_state=runtime_state)

    def get_class_folder_path(self) -> str:
        """Return the absolute path to the folder where this agent was instantiated."""
        from agency_swarm.utils.files import get_external_caller_directory

        return get_external_caller_directory()
