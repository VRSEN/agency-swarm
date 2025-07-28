import inspect
import logging
import os
import sys
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any, TypeVar

from agents import (
    Agent as BaseAgent,
    RunConfig,
    RunHooks,
    RunResult,
    Tool,
)
from openai import AsyncOpenAI, OpenAI

from .agent_core import (
    Execution,
    add_tool,
    handle_deprecated_parameters,
    load_tools_from_folder,
    parse_schemas,
    register_subagent,
    separate_kwargs,
    setup_file_manager,
)
from .context import MasterContext
from .thread import ThreadManager
from .utils.agent_file_manager import AgentFileManager

logger = logging.getLogger(__name__)

# --- Constants / Types ---
# Combine old and new params for easier checking later
AGENT_PARAMS = {
    # New/Current
    "files_folder",
    "tools_folder",
    "schemas_folder",
    "api_headers",
    "api_params",
    "description",
    "response_validator",
    # Old/Deprecated (to check in kwargs)
    "id",
    "tool_resources",
    "file_ids",
    "reasoning_effort",
    "validation_attempts",
    "examples",
    "file_search",
    "refresh_from_id",
}

# --- Constants for dynamic tool creation ---
SEND_MESSAGE_TOOL_PREFIX = "send_message_to_"
MESSAGE_PARAM = "message"

T = TypeVar("T", bound="Agent")


class Agent(BaseAgent[MasterContext]):
    """
    Agency Swarm Agent: Extends the base `agents.Agent` with capabilities for
    multi-agent collaboration within an `Agency`.

    This class manages agent-specific parameters like file folders, response validation,
    and handles the registration of subagents to enable communication within the agency
    structure defined by an `AgencyChart`. It relies on the underlying `agents` SDK
    for core execution logic via the `Runner`.

    Attributes:
        files_folder (str | Path | None): Path to a local folder for managing files associated with this agent.
                                          If the folder name follows the pattern `*_vs_<vector_store_id>`,
                                          files uploaded via `upload_file` will also be added to the specified
                                          OpenAI Vector Store, and a `FileSearchTool` will be automatically added.
        tools_folder (str | Path | None): Path to a directory containing tool definitions. Tools are automatically
                                           discovered and loaded from this directory. Supports both BaseTool
                                           subclasses and FunctionTool instances. Python files starting with
                                           underscore are ignored.
        description (str | None): A description of the agent's role or purpose, used when generating
                                  dynamic `send_message` tools for other agents.
        output_type (type[Any] | None): The type of the agent's final output.
        send_message_tool_class (type | None): Custom SendMessage tool class to use for inter-agent communication.
                                               If None, uses the default SendMessage class.
        include_search_results (bool): Whether to include search results in FileSearchTool output for citation extraction.
                                      Defaults to False for backward compatibility.
        _thread_manager (ThreadManager | None): Internal reference to the agency's `ThreadManager`.
                                                Set by the parent `Agency`.
        _agency_instance (Any | None): Internal reference to the parent `Agency` instance. Set by the parent `Agency`.
        _associated_vector_store_id (str | None): The ID of the OpenAI Vector Store associated via `files_folder`.
        files_folder_path (Path | None): The resolved absolute path for `files_folder`.
        _subagents (dict[str, "Agent"]): Dictionary mapping names of registered subagents to their instances.
        _openai_client (AsyncOpenAI | None): Internal reference to the initialized AsyncOpenAI client instance.
        _openai_client_sync (OpenAI | None): Internal reference to the initialized sync OpenAI client instance.
        file_manager (AgentFileManager | None): File management utility for handling file uploads and vector stores.
        _load_threads_callback (Callable[[], dict[str, Any]] | None): Callback to load all thread data.
        _save_threads_callback (Callable[[dict[str, Any]], None] | None): Callback to save all threads data.
    """

    # --- Agency Swarm Specific Parameters ---
    files_folder: str | Path | None
    tools_folder: str | Path | None  # Directory path for automatic tool discovery and loading
    description: str | None
    output_type: type[Any] | None
    send_message_tool_class: type | None  # Custom SendMessage tool class for inter-agent communication
    include_search_results: bool = False

    # --- Internal State ---
    _thread_manager: ThreadManager | None = None
    _agency_instance: Any | None = None  # Holds reference to parent Agency
    _associated_vector_store_id: str | None = None
    files_folder_path: Path | None = None
    _subagents: dict[str, "Agent"]
    _openai_client: AsyncOpenAI | None = None
    _openai_client_sync: OpenAI | None = None
    file_manager: AgentFileManager | None = None
    _load_threads_callback: Callable[[], dict[str, Any]] | None = None
    _save_threads_callback: Callable[[dict[str, Any]], None] | None = None

    # --- SDK Agent Compatibility ---
    # Re-declare attributes from BaseAgent for clarity and potential overrides

    def __init__(self, **kwargs: Any):
        """
        Initializes the Agency Swarm Agent.

        Handles backward compatibility with deprecated parameters from older versions
        of Agency Swarm and passes relevant parameters to the base `agents.Agent` constructor.
        Initializes file handling based on `files_folder` and the internal subagent dictionary.

        Args:
            **kwargs: Keyword arguments including standard `agents.Agent` parameters
                      (like `name`, `instructions`, `model`, `tools`, `hooks`, etc.)
                      and Agency Swarm specific parameters (`files_folder`, `description`,
                      `output_type`, `load_threads_callback`, `save_threads_callback`).
                      Deprecated parameters are handled with warnings.

        Raises:
            ValueError: If the required 'name' parameter is not provided.
            TypeError: If the 'tools' parameter is provided but is not a list.
        """
        # Handle deprecated parameters
        handle_deprecated_parameters(kwargs)

        # Separate kwargs into base agent params and agency swarm params
        base_agent_params, current_agent_params = separate_kwargs(kwargs)

        # Validate required parameters
        if "name" not in base_agent_params:
            raise ValueError("Agent requires a 'name' parameter.")
        if "tools" not in base_agent_params:
            base_agent_params["tools"] = []
        elif not isinstance(base_agent_params["tools"], list):
            raise TypeError("'tools' parameter must be a list.")

        # Remove description from base_agent_params if it was added for Swarm Agent
        base_agent_params.pop("description", None)

        # Initialize base agent
        super().__init__(**base_agent_params)

        # Initialize Agency Swarm specific attributes
        self.files_folder = current_agent_params.get("files_folder")
        self.tools_folder = current_agent_params.get("tools_folder")
        self.schemas_folder = current_agent_params.get("schemas_folder", [])
        self.api_headers = current_agent_params.get("api_headers", {})
        self.api_params = current_agent_params.get("api_params", {})
        self.description = current_agent_params.get("description")
        self.send_message_tool_class = current_agent_params.get("send_message_tool_class")
        self.include_search_results = current_agent_params.get("include_search_results", False)

        # Persistence callbacks
        self._load_threads_callback = current_agent_params.get("load_threads_callback")
        self._save_threads_callback = current_agent_params.get("save_threads_callback")

        # Internal state
        self._openai_client = None
        self._openai_client_sync = None
        self._subagents = {}

        # Initialize execution handler
        self._execution = Execution(self)

        # Set files_folder_path
        if self.files_folder:
            self.files_folder_path = Path(self.files_folder).resolve()
        else:
            self.files_folder_path = None

        # Set up file manager and tools
        setup_file_manager(self, self.files_folder)
        parse_schemas(self)
        load_tools_from_folder(self)

    # --- Properties ---
    def __repr__(self) -> str:
        """Return a string representation of the Agent instance."""
        # Get model information - try model_settings.model first, then fall back to model attribute
        model_info = "unknown"
        if hasattr(self, "model_settings") and self.model_settings and hasattr(self.model_settings, "model"):
            model_info = self.model_settings.model
        elif hasattr(self, "model") and self.model:
            model_info = self.model

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

    # --- Subagent Management ---
    def register_subagent(self, recipient_agent: "Agent") -> None:
        """
        Registers another agent as a subagent that this agent can communicate with.

        This method stores a reference to the recipient agent and dynamically creates
        and adds a specific `FunctionTool` named `send_message_to_<RecipientName>`
        to this agent's tools. This allows the agent to call the recipient agent
        during a run using the standard tool invocation mechanism.

        Args:
            recipient_agent (Agent): The `Agent` instance to register as a recipient.

        Raises:
            TypeError: If `recipient_agent` is not a valid `Agent` instance or lacks a name.
            ValueError: If attempting to register the agent itself as a subagent.
        """
        register_subagent(self, recipient_agent)

    # --- File Handling ---
    def upload_file(self, file_path: str, include_in_vector_store: bool = True) -> str:
        """Upload a file using the agent's file manager."""
        return self.file_manager.upload_file(file_path, include_in_vector_store)

    # --- Core Execution Methods ---
    async def get_response(
        self,
        message: str | list[dict[str, Any]],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        message_files: list[str] | None = None,  # Backward compatibility
        file_ids: list[str] | None = None,  # New parameter
        additional_instructions: str | None = None,
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
            run_config: Optional run configuration settings
            message_files: DEPRECATED: Use file_ids instead. File IDs to attach to the message
            file_ids: List of OpenAI file IDs to attach to the message
            additional_instructions: Additional instructions to be appended to the agent's instructions for this run only
            **kwargs: Additional keyword arguments including max_turns

        Returns:
            RunResult: The complete execution result
        """

        return await self._execution.get_response(
            message=message,
            sender_name=sender_name,
            context_override=context_override,
            hooks_override=hooks_override,
            run_config_override=run_config_override,
            message_files=message_files,
            file_ids=file_ids,
            additional_instructions=additional_instructions,
            **kwargs,
        )

    async def get_response_stream(
        self,
        message: str | list[dict[str, Any]],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        message_files: list[str] | None = None,
        file_ids: list[str] | None = None,
        additional_instructions: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any]:
        """Runs the agent's turn in streaming mode.

        Args:
            message: The input message or list of message items
            sender_name: Name of the sending agent (None for user interactions)
            context_override: Optional context data to override default values
            hooks_override: Optional hooks to override default agent hooks
            run_config_override: Optional run configuration
            additional_instructions: Additional instructions to be appended to the agent's instructions for this run only
            **kwargs: Additional keyword arguments

        Yields:
            Stream events from the agent's execution
        """

        async for event in self._execution.get_response_stream(
            message=message,
            sender_name=sender_name,
            context_override=context_override,
            hooks_override=hooks_override,
            run_config_override=run_config_override,
            message_files=message_files,
            file_ids=file_ids,
            additional_instructions=additional_instructions,
            **kwargs,
        ):
            yield event

    # --- Helper Methods ---
    def get_thread_id(self, sender_name: str | None = None) -> str:
        """Construct a thread identifier based on sender and recipient names."""
        sender = sender_name or "user"
        return f"{sender}->{self.name}"

    # _validate_response removed - use output_guardrails instead

    # --- Agency Configuration Methods --- (Called by Agency)
    def _set_thread_manager(self, manager: ThreadManager):
        """Allows the Agency to inject the ThreadManager instance."""
        self._thread_manager = manager

    def _set_agency_instance(self, agency: Any):
        """Allows the Agency to inject a reference to itself and its agent map.

        Prevents agent instance sharing between agencies to avoid callback and ThreadManager conflicts.
        """
        if not hasattr(agency, "agents"):
            raise TypeError("Provided agency instance must have an 'agents' dictionary.")

        # Check if agent is already owned by a different agency
        if hasattr(self, "_agency_instance") and self._agency_instance is not None:
            if self._agency_instance is not agency:
                agency_name = getattr(agency, "name", "unnamed")
                existing_agency_name = getattr(self._agency_instance, "name", "unnamed")
                raise ValueError(
                    f"Agent '{self.name}' is already registered in agency '{existing_agency_name}'. "
                    f"Each agent instance can only belong to one agency to prevent callback conflicts. "
                    f"To use the same agent logic in multiple agencies, create separate agent instances:\n"
                    f"  agent1 = Agent(name='{self.name}', instructions='...', ...)\n"
                    f"  agent2 = Agent(name='{self.name}', instructions='...', ...)\n"
                    f"Then use agent1 in one agency and agent2 in another."
                )
            # Agent is already registered in this agency, allow re-configuration
            agency_name = getattr(agency, "name", "unnamed")
            logger.debug(
                f"Agent '{self.name}' already registered in agency '{agency_name}', skipping duplicate registration."
            )
            return

        self._agency_instance = agency

    def _set_persistence_callbacks(
        self,
        load_threads_callback: Callable[[], dict[str, Any]] | None = None,
        save_threads_callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        """Set persistence callbacks for the agent's thread manager.

        This method allows setting callbacks after agent initialization and will
        create a new ThreadManager with the provided callbacks if none exists.

        Args:
            load_threads_callback: Callback to load all thread data
            save_threads_callback: Callback to save all threads data
        """
        self._load_threads_callback = load_threads_callback
        self._save_threads_callback = save_threads_callback

        # Create ThreadManager with callbacks if it doesn't exist
        if self._thread_manager is None:
            self._thread_manager = ThreadManager(
                load_threads_callback=load_threads_callback, save_threads_callback=save_threads_callback
            )

    def _ensure_thread_manager(self):
        """Ensures the agent has a ThreadManager, creating one if necessary.

        This is called when the agent is used directly without an Agency.
        """
        if self._thread_manager is None:
            self._thread_manager = ThreadManager(
                load_threads_callback=self._load_threads_callback, save_threads_callback=self._save_threads_callback
            )

    def get_class_folder_path(self) -> str:
        """Return the absolute path to the folder containing this class."""
        module = sys.modules.get(self.__class__.__module__)
        if module and getattr(module, "__file__", None):
            return os.path.abspath(os.path.dirname(module.__file__))

        try:
            class_file = inspect.getfile(self.__class__)
        except (TypeError, OSError, AttributeError):
            return "./"
        return os.path.abspath(os.path.realpath(os.path.dirname(class_file)))
