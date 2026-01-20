import asyncio
import logging
import os
from pathlib import Path
from typing import Annotated, Any, TypeVar

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
from pydantic import StringConstraints, TypeAdapter, ValidationError

from agency_swarm.agent import (
    Execution,
    add_tool,
    apply_framework_defaults,
    load_tools_from_folder,
    normalize_agent_tool_definitions,
    parse_schemas,
    separate_kwargs,
    setup_file_manager,
    validate_no_deprecated_agent_kwargs,
    validate_tools,
    wrap_input_guardrails,
)
from agency_swarm.agent.agent_flow import AgentFlow
from agency_swarm.agent.attachment_manager import AttachmentManager
from agency_swarm.agent.conversation_starters_cache import (
    compute_starter_cache_fingerprint,
    load_cached_starter,
    load_cached_starters,
    normalize_starter_text,
)
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
    structure defined by entry points and communication flows. It relies on the underlying `agents` SDK
    for core execution logic via the `Runner`.

    Agents are stateless. Agency-specific resources like thread managers,
    subagent mappings and shared instructions are provided at runtime via
    :class:`AgencyContext` from the owning :class:`Agency`.
    """

    # --- Agency Swarm Specific Parameters ---
    files_folder: str | Path | None
    tools_folder: str | Path | None  # Directory path for automatic tool discovery and loading
    description: str | None
    conversation_starters: list[str] | None
    cache_conversation_starters: bool = False
    output_type: type[Any] | None
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
    _conversation_starters_cache: dict[str, Any]
    _conversation_starters_fingerprint: str | None
    _conversation_starters_warmup_started: bool

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
            conversation_starters (list[str] | None): Conversation starters for this agent.
            cache_conversation_starters (bool): Enable cached conversation starters from .agency_swarm.
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
        validate_no_deprecated_agent_kwargs(kwargs)
        normalize_agent_tool_definitions(kwargs)

        # Apply framework defaults (e.g., truncation="auto")
        apply_framework_defaults(kwargs)

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
            # Validate that tools are properly initialized and supported
            validate_tools(tools_list)

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
        conversation_starters = current_agent_params.get("conversation_starters")
        self.conversation_starters = _validate_conversation_starters(conversation_starters)
        cache_enabled = current_agent_params.get("cache_conversation_starters", False)
        self.cache_conversation_starters = _validate_cache_conversation_starters(cache_enabled)
        self.send_message_tool_class = current_agent_params.get("send_message_tool_class")
        self.include_search_results = current_agent_params.get("include_search_results", False)
        self.validation_attempts = int(current_agent_params.get("validation_attempts", 1))
        self.throw_input_guardrail_error = bool(current_agent_params.get("throw_input_guardrail_error", False))
        self.handoff_reminder = current_agent_params.get("handoff_reminder")

        # Internal state
        self._openai_client = None
        self._openai_client_sync = None
        self._tool_concurrency_manager = ToolConcurrencyManager()
        self._conversation_starters_cache = {}
        self._conversation_starters_fingerprint = None
        self._conversation_starters_warmup_started = False

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

        # Refresh after MCP conversion so fingerprint includes MCP-converted tools
        self.refresh_conversation_starters_cache()

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

        master_context = run_context.context
        runtime_tools: list[Tool] = []
        if master_context:
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
            file_ids=file_ids,
            additional_instructions=additional_instructions,
            agency_context=agency_context,
            **kwargs,
        )

    def refresh_conversation_starters_cache(self, runtime_state: AgentRuntimeState | None = None) -> None:
        """Recompute conversation starter cache fingerprint and reload cached entries."""
        if not self.cache_conversation_starters:
            return
        if not self.conversation_starters:
            return

        fingerprint = compute_starter_cache_fingerprint(self, runtime_state=runtime_state)
        if fingerprint == self._conversation_starters_fingerprint and self._conversation_starters_cache:
            return

        self._conversation_starters_fingerprint = fingerprint
        self._conversation_starters_cache = load_cached_starters(
            self.name,
            self.conversation_starters,
            expected_fingerprint=fingerprint,
        )

    async def warm_conversation_starters_cache(self, agency_context: AgencyContext | None = None) -> None:
        """Populate missing conversation starters cache entries using the model."""
        if not self.cache_conversation_starters:
            return
        if not self.conversation_starters:
            return
        if self._conversation_starters_warmup_started:
            return
        self._conversation_starters_warmup_started = True

        cache_map = self._conversation_starters_cache
        fingerprint = self._conversation_starters_fingerprint
        missing: list[str] = []
        for starter in self.conversation_starters:
            normalized = normalize_starter_text(starter)
            if normalized and normalized not in cache_map:
                cached = load_cached_starter(self.name, starter, expected_fingerprint=fingerprint)
                if cached:
                    cache_map[normalized] = cached
                else:
                    missing.append(starter)

        if not missing:
            return

        await asyncio.gather(
            *(
                self.get_response(
                    message=starter,
                    sender_name=None,
                    agency_context=self._create_minimal_context(
                        agency_instance=agency_context.agency_instance if agency_context else None,
                        shared_instructions=agency_context.shared_instructions if agency_context else None,
                        runtime_state=agency_context.runtime_state if agency_context else None,
                    ),
                )
                for starter in missing
            )
        )

    # --- Helper Methods ---
    # _validate_response removed - use output_guardrails instead

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

    def _create_minimal_context(
        self,
        *,
        agency_instance: Any | None = None,
        shared_instructions: str | None = None,
        runtime_state: AgentRuntimeState | None = None,
    ) -> AgencyContext:
        """Create a minimal context for standalone agent usage (no agency)."""
        from ..utils.thread import ThreadManager

        thread_manager = ThreadManager()
        resolved_runtime_state = runtime_state or AgentRuntimeState(self._tool_concurrency_manager)
        return AgencyContext(
            agency_instance=agency_instance,
            thread_manager=thread_manager,
            runtime_state=resolved_runtime_state,
            load_threads_callback=None,
            save_threads_callback=None,
            shared_instructions=shared_instructions,
        )


_NON_EMPTY_STR = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


_CONVERSATION_STARTERS_ADAPTER = TypeAdapter(list[_NON_EMPTY_STR])


def _validate_conversation_starters(value: Any) -> list[str] | None:
    if value is None:
        return None
    try:
        return _CONVERSATION_STARTERS_ADAPTER.validate_python(value)
    except ValidationError as exc:
        raise ValueError("conversation_starters must be a list of non-empty strings") from exc


def _validate_cache_conversation_starters(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    raise ValueError("cache_conversation_starters must be a boolean")
