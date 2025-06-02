import asyncio
import inspect
import json
import logging
import os
import warnings
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any, TypeVar

from agents import (
    Agent as BaseAgent,
    FileSearchTool,
    RunConfig,
    RunHooks,
    RunItem,
    Runner,
    RunResult,
    Tool,
    TResponseInputItem,
)
from agents.exceptions import AgentsException
from agents.items import (
    ItemHelpers,
    MessageOutputItem,
    ToolCallItem,
    ToolCallOutputItem,
)
from agents.run import DEFAULT_MAX_TURNS
from agents.stream_events import RunItemStreamEvent
from agents.strict_schema import ensure_strict_json_schema
from agents.tool import FunctionTool
from openai import AsyncOpenAI, NotFoundError, OpenAI
from openai.types.responses import ResponseFileSearchToolCall, ResponseFunctionToolCall

from .context import MasterContext
from .thread import ThreadManager
from .tools import BaseTool
from .tools.send_message import SendMessage
from .tools.utils import from_openapi_schema, validate_openapi_spec
from .utils.agent_file_manager import AgentFileManager

logger = logging.getLogger(__name__)

# --- Constants / Types ---
# Combine old and new params for easier checking later
AGENT_PARAMS = {
    # New/Current
    "files_folder",
    "tools_folder",
    "description",
    "response_validator",
    # Old/Deprecated (to check in kwargs)
    "id",
    "tool_resources",
    "schemas_folder",
    "api_headers",
    "api_params",
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
        tools_folder (str | Path | None): Placeholder for future functionality to load tools from a directory.
        description (str | None): A description of the agent's role or purpose, used when generating
                                  dynamic `send_message` tools for other agents.
        response_validator (Callable[[str], bool] | None): An optional callable that validates the agent's
                                                          final text response. It should return `True` if the
                                                          response is valid, `False` otherwise.
        output_type (type[Any] | None): The type of the agent's final output.
        _thread_manager (ThreadManager | None): Internal reference to the agency's `ThreadManager`.
                                                Set by the parent `Agency`.
        _agency_instance (Any | None): Internal reference to the parent `Agency` instance. Set by the parent `Agency`.
        _associated_vector_store_id (str | None): The ID of the OpenAI Vector Store associated via `files_folder`.
        files_folder_path (Path | None): The resolved absolute path for `files_folder`.
        _subagents (dict[str, "Agent"]): Dictionary mapping names of registered subagents to their instances.
        _openai_client (AsyncOpenAI | None): Internal reference to the initialized AsyncOpenAI client instance.
        _openai_client_sync (OpenAI | None): Internal reference to the initialized sync OpenAI client instance.
        file_manager (AgentFileManager | None): File management utility for handling file uploads and vector stores.
        _load_threads_callback (Callable[[str], dict[str, Any] | None] | None): Callback to load thread data by thread_id.
        _save_threads_callback (Callable[[dict[str, Any]], None] | None): Callback to save all threads data.
    """

    # --- Agency Swarm Specific Parameters ---
    files_folder: str | Path | None
    tools_folder: str | Path | None  # Placeholder for future ToolFactory
    description: str | None
    response_validator: Callable[[str], bool] | None
    output_type: type[Any] | None  # Add output_type parameter

    # --- Internal State ---
    _thread_manager: ThreadManager | None = None
    _agency_instance: Any | None = None  # Holds reference to parent Agency
    _associated_vector_store_id: str | None = None
    files_folder_path: Path | None = None
    _subagents: dict[str, "Agent"]
    _openai_client: AsyncOpenAI | None = None
    _openai_client_sync: OpenAI | None = None
    file_manager: AgentFileManager | None = None
    _load_threads_callback: Callable[[str], dict[str, Any] | None] | None = None
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
                      `response_validator`, `output_type`, `load_threads_callback`, `save_threads_callback`).
                      Deprecated parameters are handled with warnings.

        Raises:
            ValueError: If the required 'name' parameter is not provided.
            TypeError: If the 'tools' parameter is provided but is not a list.
        """
        # --- Handle Deprecated Args ---
        deprecated_args_used = {}
        if "id" in kwargs:
            warnings.warn(
                "'id' parameter (OpenAI Assistant ID) is deprecated and no longer used for loading. Agent state is managed via PersistenceHooks.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["id"] = kwargs.pop("id")
        if "tool_resources" in kwargs:
            warnings.warn(
                "'tool_resources' is deprecated. File resources should be managed via 'files_folder' and the 'upload_file' method for Vector Stores.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["tool_resources"] = kwargs.pop("tool_resources")
        if "schemas_folder" in kwargs or "api_headers" in kwargs or "api_params" in kwargs:
            warnings.warn(
                "'schemas_folder', 'api_headers', and 'api_params' related to OpenAPI tools are deprecated. Use standard FunctionTools instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if "file_ids" in kwargs:
            warnings.warn(
                "'file_ids' is deprecated. Use 'files_folder' to associate with Vector Stores or manage files via Agent methods.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["file_ids"] = kwargs.pop("file_ids")
        if "reasoning_effort" in kwargs:
            warnings.warn(
                "'reasoning_effort' is deprecated as a direct Agent parameter. Configure model settings via 'model_settings' if needed.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["reasoning_effort"] = kwargs.pop("reasoning_effort")
        if "validation_attempts" in kwargs:
            val_attempts = kwargs.pop("validation_attempts")
            warnings.warn(
                "'validation_attempts' is deprecated. Use the 'response_validator' callback for validation logic.",
                DeprecationWarning,
                stacklevel=2,
            )
            if val_attempts > 1 and "response_validator" not in kwargs:
                warnings.warn(
                    "Using 'validation_attempts > 1' without a 'response_validator' has no effect. Implement validation logic in the callback.",
                    UserWarning,  # Changed to UserWarning as it's about usage logic
                    stacklevel=2,
                )
            deprecated_args_used["validation_attempts"] = val_attempts
        if "examples" in kwargs:
            examples = kwargs.pop("examples")
            warnings.warn(
                "'examples' parameter is deprecated. Consider incorporating examples directly into the agent's 'instructions'.",
                DeprecationWarning,
                stacklevel=2,
            )
            # Attempt to prepend examples to instructions
            if examples and isinstance(examples, list):
                try:
                    # Basic formatting, might need refinement
                    examples_str = "\\n\\nExamples:\\n" + "\\n".join(f"- {json.dumps(ex)}" for ex in examples)
                    current_instructions = kwargs.get("instructions", "")
                    kwargs["instructions"] = current_instructions + examples_str
                    logger.info("Prepended 'examples' content to agent instructions.")
                except Exception as e:
                    logger.warning(f"Could not automatically prepend 'examples' to instructions: {e}")
            deprecated_args_used["examples"] = examples  # Store original for logging if needed
        if "file_search" in kwargs:
            warnings.warn(
                "'file_search' parameter is deprecated. FileSearchTool is added automatically if 'files_folder' indicates a Vector Store.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["file_search"] = kwargs.pop("file_search")
        if "refresh_from_id" in kwargs:
            warnings.warn(
                "'refresh_from_id' is deprecated as loading by Assistant ID is no longer supported.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["refresh_from_id"] = kwargs.pop("refresh_from_id")

        if "tools" in kwargs:
            tools_list = kwargs["tools"]
            for i, tool in enumerate(tools_list):
                if isinstance(tool, type) and issubclass(tool, BaseTool):
                    warnings.warn(
                        "'BaseTool' class is deprecated. Consider switching to FunctionTool.",
                        DeprecationWarning,
                        stacklevel=2,
                    )
                    tools_list[i] = self._adapt_legacy_tool(tool)

        # Log if any deprecated args were used
        if deprecated_args_used:
            logger.warning(f"Deprecated Agent parameters used: {list(deprecated_args_used.keys())}")

        # --- Separate Kwargs ---
        base_agent_params = {}
        current_agent_params = {}
        # --- Get BaseAgent signature ---
        try:
            base_sig = inspect.signature(BaseAgent)
            base_param_names = set(base_sig.parameters.keys())
        except ValueError:
            # Fallback if signature inspection fails
            base_param_names = {
                "name",
                "instructions",
                "handoff_description",
                "handoffs",
                "model",
                "model_settings",
                "tools",
                "mcp_servers",
                "mcp_config",
                "input_guardrails",
                "output_guardrails",
                "output_type",
                "hooks",
                "tool_use_behavior",
                "reset_tool_choice",
            }

        # Iterate through remaining kwargs after popping deprecated ones
        for key, value in kwargs.items():
            if key in base_param_names:
                base_agent_params[key] = value
            # Swarm-specific parameters
            elif key in {
                "files_folder",
                "tools_folder",
                "schemas_folder",
                "api_headers",
                "api_params",
                "response_validator",
                "description",
                "load_threads_callback",
                "save_threads_callback",
            }:
                current_agent_params[key] = value
            else:
                # Only warn if it wasn't a handled deprecated arg
                if key not in deprecated_args_used:
                    logger.warning(f"Unknown parameter '{key}' passed to Agent constructor.")

        # --- BaseAgent Init ---
        if "name" not in base_agent_params:
            raise ValueError("Agent requires a 'name' parameter.")
        if "tools" not in base_agent_params:
            base_agent_params["tools"] = []
        elif not isinstance(base_agent_params["tools"], list):
            raise TypeError("'tools' parameter must be a list.")
        # Remove description from base_agent_params if it was added for Swarm Agent
        # BaseAgent might have its own description or similar param, but Swarm's `description`
        # is for inter-agent communication tool generation.
        base_agent_params.pop("description", None)

        super().__init__(**base_agent_params)

        # --- Agency Swarm Attrs Init --- (Assign AFTER super)
        self.files_folder = current_agent_params.get("files_folder")
        self.tools_folder = current_agent_params.get("tools_folder")
        self.schemas_folder = current_agent_params.get("schemas_folder", [])
        self.api_headers = current_agent_params.get("api_headers", {})
        self.api_params = current_agent_params.get("api_params", {})
        self.response_validator = current_agent_params.get("response_validator")
        # Set description directly from current_agent_params, default to None if not provided
        self.description = current_agent_params.get("description")
        # output_type is handled by the base Agent constructor, no need to set it here

        # --- Persistence Callbacks ---
        self._load_threads_callback = current_agent_params.get("load_threads_callback")
        self._save_threads_callback = current_agent_params.get("save_threads_callback")

        # --- Internal State Init ---
        self._openai_client = None
        # Needed for file operations
        self._openai_client_sync = OpenAI()
        self._subagents = {}
        # _thread_manager and _agency_instance are injected by Agency

        self.file_manager = AgentFileManager(self)

        self.file_manager._parse_files_folder_for_vs_id()
        self._parse_schemas()
        # The full async _init_file_handling (with VS retrieval) should be called by Agency or explicitly in tests.

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
        # Simplified: Assumes tool is already a valid Tool instance
        if not isinstance(tool, Tool):
            raise TypeError(f"Expected an instance of agents.Tool, got {type(tool)}")

        # Check for existing tool with the same name before adding
        if any(getattr(t, "name", None) == getattr(tool, "name", None) for t in self.tools):
            logger.warning(
                f"Tool with name '{getattr(tool, 'name', '(unknown)')}' already exists for agent '{self.name}'. Skipping."
            )
            return

        self.tools.append(tool)
        logger.debug(f"Tool '{getattr(tool, 'name', '(unknown)')}' added to agent '{self.name}'")

    def _load_tools_from_folder(self) -> None:
        """Placeholder: Loads tools from tools_folder (future Task)."""
        if self.tools_folder:
            logger.warning("Tool loading from folder is not fully implemented yet.")
            # Placeholder logic using ToolFactoryPlaceholder (replace when implemented)
            # try:
            #     folder_path = Path(self.tools_folder).resolve()
            #     loaded_tools = ToolFactory.load_tools_from_folder(folder_path)
            #     for tool in loaded_tools:
            #         self.add_tool(tool)
            # except Exception as e:
            #     logger.error(f"Error loading tools from folder {self.tools_folder}: {e}")

    def _parse_schemas(self):
        schemas_folders = self.schemas_folder if isinstance(self.schemas_folder, list) else [self.schemas_folder]

        for schemas_folder in schemas_folders:
            if isinstance(schemas_folder, str):
                f_path = schemas_folder

                if not os.path.isdir(f_path):
                    f_path = os.path.join(self._get_class_folder_path(), schemas_folder)
                    f_path = os.path.normpath(f_path)

                if os.path.isdir(f_path):
                    f_paths = os.listdir(f_path)

                    f_paths = [f for f in f_paths if not f.startswith(".")]

                    f_paths = [os.path.join(f_path, f) for f in f_paths]

                    for f_path in f_paths:
                        with open(f_path) as f:
                            openapi_spec = f.read()
                            f.close()  # fix permission error on windows
                        try:
                            validate_openapi_spec(openapi_spec)
                        except Exception as e:
                            logger.error("Invalid OpenAPI schema: " + os.path.basename(f_path))
                            raise e
                        try:
                            headers = None
                            params = None
                            if os.path.basename(f_path) in self.api_headers:
                                headers = self.api_headers[os.path.basename(f_path)]
                            if os.path.basename(f_path) in self.api_params:
                                params = self.api_params[os.path.basename(f_path)]
                            tools = from_openapi_schema(openapi_spec, headers=headers, params=params)
                        except Exception as e:
                            logger.error(
                                "Error parsing OpenAPI schema: " + os.path.basename(f_path),
                                exc_info=True,
                            )
                            raise e
                        for tool in tools:
                            logger.info(f"Adding tool {tool.name} from {f_path}")
                            self.add_tool(tool)
                else:
                    logger.warning("Schemas folder path is not a directory. Skipping... ", f_path)
            else:
                logger.warning(
                    "Schemas folder path must be a string or list of strings. Skipping... ",
                    schemas_folder,
                )

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
        if not isinstance(recipient_agent, Agent):
            raise TypeError(
                f"Expected an instance of Agent, got {type(recipient_agent)}. Ensure agents are initialized before registration."
            )
        if not hasattr(recipient_agent, "name") or not isinstance(recipient_agent.name, str):
            raise TypeError("Subagent must be an Agent instance with a valid name.")

        recipient_name = recipient_agent.name
        if recipient_name == self.name:
            raise ValueError("Agent cannot register itself as a subagent.")

        # Initialize _subagents if it doesn't exist
        if not hasattr(self, "_subagents") or self._subagents is None:
            self._subagents = {}

        if recipient_name in self._subagents:
            logger.warning(
                f"Agent '{recipient_name}' is already registered as a subagent for '{self.name}'. Skipping tool creation."
            )
            return

        self._subagents[recipient_name] = recipient_agent
        logger.info(f"Agent '{self.name}' registered subagent: '{recipient_name}'")

        # --- Dynamically create the specific send_message tool --- #

        tool_name = f"{SEND_MESSAGE_TOOL_PREFIX}{recipient_name}"

        send_message_tool_instance = SendMessage(
            tool_name=tool_name,
            sender_agent=self,
            recipient_agent=recipient_agent,
        )

        # Add the specific tool to this agent's tools
        self.add_tool(send_message_tool_instance)
        logger.debug(f"Dynamically added tool '{tool_name}' to agent '{self.name}'.")

    # --- File Handling ---
    async def _init_file_handling(self) -> None:
        """
        Asynchronously initializes file handling by verifying/retrieving the
        associated Vector Store on OpenAI if an ID was parsed.
        This method should be called after agent instantiation in an async context.
        """
        # Ensure synchronous parts have run (idempotent checks or rely on __init__ call)
        if self.files_folder and not self.files_folder_path:
            self.file_manager._parse_files_folder_for_vs_id()  # Ensure path and tentative VS ID are set

        if not self._associated_vector_store_id or not self.files_folder_path:
            logger.debug(f"Agent {self.name}: Skipping async VS check. No VS ID parsed or files_folder_path not set.")
            return

        # If a vector store ID is associated AND local folder path is valid
        try:
            # Attempt to retrieve the Vector Store by ID
            vector_store = await self.client.vector_stores.retrieve(vector_store_id=self._associated_vector_store_id)
            logger.info(
                f"Agent {self.name}: Successfully retrieved existing Vector Store '{vector_store.id}' ('{vector_store.name}')."
            )
        except NotFoundError:
            logger.error(
                f"Agent {self.name}: Vector Store ID '{self._associated_vector_store_id}' provided in files_folder was not found on OpenAI. "
                f"FileSearchTool might not be effective or may need manual VS creation and ID update."
            )
            # Decide if we should nullify _associated_vector_store_id here or just warn.
            # For now, keep the ID but log error. User might create it later.
            # Or, to be safer and prevent use of a non-existent VS:
            # self._associated_vector_store_id = None
            # self.tools = [t for t in self.tools if not isinstance(t, FileSearchTool)] # Remove FileSearchTool
        except Exception as e_retrieve:
            logger.error(
                f"Agent {self.name}: Error retrieving Vector Store '{self._associated_vector_store_id}': {e_retrieve}"
            )
            # Similar decision: nullify or just warn.
            # self._associated_vector_store_id = None
            # self.tools = [t for t in self.tools if not isinstance(t, FileSearchTool)]

    # Expose the upload_file method from the file_manager for ease of access
    def upload_file(self, file_path: str, include_in_vector_store: bool = True) -> str:
        """Upload a file using the agent's file manager."""
        return self.file_manager.upload_file(file_path, include_in_vector_store)

    async def check_file_exists(self, file_name_or_path: str) -> str | None:
        """Check if a file exists using the agent's file manager."""
        if not self.file_manager or not self.files_folder_path:
            return None
        try:
            return self.file_manager.get_id_from_file(file_name_or_path)
        except FileNotFoundError:
            return None

    # --- Core Execution Methods ---
    async def get_response(
        self,
        message: str | list[dict[str, Any]],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config: RunConfig | None = None,
        message_files: list[str] | None = None,  # Backward compatibility
        file_ids: list[str] | None = None,  # New parameter
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
            **kwargs: Additional keyword arguments including max_turns

        Returns:
            RunResult: The complete execution result
        """
        # Ensure ThreadManager exists (for direct agent usage without Agency)
        self._ensure_thread_manager()

        if not self._thread_manager:
            raise RuntimeError(f"Agent '{self.name}' missing ThreadManager.")

        # For direct agent usage, we need to ensure _agency_instance exists with minimal agents map
        if not self._agency_instance or not hasattr(self._agency_instance, "agents"):
            if sender_name is None:  # Direct user interaction without agency
                # Create a minimal agency-like object for compatibility
                class MinimalAgency:
                    def __init__(self, agent):
                        self.agents = {agent.name: agent}
                        self.user_context = {}

                self._agency_instance = MinimalAgency(self)
            else:
                raise RuntimeError(f"Agent '{self.name}' missing Agency instance for agent-to-agent communication.")

        # Generate a thread identifier based on communication context
        thread_id = self.get_thread_id(sender_name)
        logger.info(f"Agent '{self.name}' handling get_response for thread: {thread_id}")
        thread = self._thread_manager.get_thread(thread_id)

        processed_current_message_items: list[TResponseInputItem]
        try:
            processed_current_message_items = ItemHelpers.input_to_new_input_list(message)
        except Exception as e:
            logger.error(f"Error processing current input message for get_response: {e}", exc_info=True)
            raise AgentsException(f"Failed to process input message for agent {self.name}") from e

        # Handle file attachments - support both old message_files and new file_ids
        files_to_attach = file_ids or message_files or kwargs.get("file_ids") or kwargs.get("message_files")
        if files_to_attach and isinstance(files_to_attach, list):
            # Warn about deprecated message_files usage
            if message_files or kwargs.get("message_files"):
                warnings.warn(
                    "'message_files' parameter is deprecated. Use 'file_ids' instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )

            # Add file items to the last user message content
            if processed_current_message_items:
                last_message = processed_current_message_items[-1]
                if isinstance(last_message, dict) and last_message.get("role") == "user":
                    # Ensure content is a list for multi-content messages
                    current_content = last_message.get("content", "")
                    if isinstance(current_content, str):
                        # Convert string content to list format
                        content_list = [{"type": "input_text", "text": current_content}] if current_content else []
                    elif isinstance(current_content, list):
                        content_list = list(current_content)
                    else:
                        content_list = []

                    # Add file items to content
                    for file_id in files_to_attach:
                        if isinstance(file_id, str) and file_id.startswith("file-"):
                            file_content_item = {
                                "type": "input_file",
                                "file_id": file_id,
                            }
                            content_list.append(file_content_item)
                            logger.debug(f"Added file content item for file_id: {file_id}")
                        else:
                            logger.warning(f"Invalid file_id format: {file_id} for agent {self.name}")

                    # Update the message content
                    last_message["content"] = content_list
                else:
                    logger.warning(f"Cannot attach files: Last message is not a user message for agent {self.name}")
            else:
                logger.warning(f"Cannot attach files: No messages to attach to for agent {self.name}")

        history_for_runner: list[TResponseInputItem]
        if sender_name is None:  # Top-level call from user or agency
            self._thread_manager.add_items_and_save(thread, processed_current_message_items)
            logger.debug(f"Added current message to shared thread {thread.thread_id} for top-level call.")
            history_for_runner = list(thread.items)  # Get full history after adding
        else:  # Agent-to-agent call (e.g., via SendMessage tool)
            # For sub-calls, the history for the runner is the current shared thread items
            # PLUS the processed current message items for this specific agent's turn.
            # These `processed_current_message_items` have been converted by ItemHelpers
            # but have not been through `thread.add_item`'s specific normalization yet,
            # which is fine as they are only for this Runner's input, not direct thread storage here.
            history_up_to_this_call = list(thread.items)
            history_for_runner = history_up_to_this_call + processed_current_message_items
            logger.debug(
                f"Constructed temporary history for sub-agent '{self.name}' run. Shared thread not modified with this input."
            )

        # The history_for_runner now contains OpenAI-compatible message dictionaries.
        # It should include user, assistant (possibly with tool_calls), and tool messages if they are part of the conversation.
        # No filtering is applied here based on user instruction.

        # Sanitize tool_calls for OpenAI /v1/responses API compliance
        history_for_runner = self._sanitize_tool_calls_in_history(history_for_runner)

        logger.info(
            f"AGENT_GET_RESPONSE: History for Runner in agent '{self.name}' for thread '{thread_id}' (length {len(history_for_runner)}):"
        )
        for i, history_item in enumerate(history_for_runner):
            # Limiting log length for potentially long content
            content_preview = str(history_item.get("content"))[:100]
            tool_calls_preview = str(history_item.get("tool_calls"))[:100]
            logger.info(
                f"AGENT_GET_RESPONSE: History item [{i}]: role={history_item.get('role')}, content='{content_preview}...', tool_calls='{tool_calls_preview}...'"
            )

        try:
            logger.debug(f"Calling Runner.run for agent '{self.name}' with {len(history_for_runner)} history items.")
            run_result: RunResult = await Runner.run(
                starting_agent=self,
                input=history_for_runner,
                context=self._prepare_master_context(context_override),
                hooks=hooks_override or self.hooks,
                run_config=run_config or RunConfig(),
                max_turns=kwargs.get("max_turns", DEFAULT_MAX_TURNS),
            )
            completion_info = (
                f"Output Type: {type(run_result.final_output).__name__}"
                if run_result.final_output is not None
                else "No final output"
            )
            logger.info(f"Runner.run completed for agent '{self.name}'. {completion_info}")

        except Exception as e:
            logger.error(f"Error during Runner.run for agent '{self.name}': {e}", exc_info=True)
            raise AgentsException(f"Runner execution failed for agent {self.name}") from e

        response_text_for_validation = ""
        if run_result.new_items:  # new_items are RunItem objects
            response_text_for_validation = ItemHelpers.text_message_outputs(run_result.new_items)

        if response_text_for_validation and self.response_validator:
            if not self._validate_response(response_text_for_validation):
                logger.warning(f"Response validation failed for agent '{self.name}'")

        if sender_name is None:  # Only save to thread if top-level call
            if self._thread_manager and run_result.new_items:
                thread = self._thread_manager.get_thread(thread_id)
                items_to_save: list[TResponseInputItem] = []
                logger.debug(
                    f"Preparing to save {len(run_result.new_items)} new items from RunResult to thread {thread.thread_id}"
                )
                for i, run_item_obj in enumerate(run_result.new_items):
                    # _run_item_to_tresponse_input_item converts RunItem to TResponseInputItem (dict)
                    item_dict = self._run_item_to_tresponse_input_item(run_item_obj)
                    if item_dict:
                        items_to_save.append(item_dict)
                        logger.debug(
                            f"  Item {i + 1}/{len(run_result.new_items)} converted for saving: {item_dict.get('role')}"
                        )
                    else:
                        logger.debug(
                            f"  Item {i + 1}/{len(run_result.new_items)} ({type(run_item_obj).__name__}) skipped or failed conversion."
                        )
                if items_to_save:
                    logger.info(f"Saving {len(items_to_save)} converted RunResult items to thread {thread.thread_id}")
                    self._thread_manager.add_items_and_save(thread, items_to_save)

        return run_result

    async def get_response_stream(
        self,
        message: str | list[dict[str, Any]],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:
        """Runs the agent's turn in streaming mode.

        Args:
            message: The input message or list of message items
            sender_name: Name of the sending agent (None for user interactions)
            context_override: Optional context data to override default values
            hooks_override: Optional hooks to override default agent hooks
            run_config_override: Optional run configuration
            **kwargs: Additional keyword arguments

        Yields:
            Stream events from the agent's execution
        """
        if message is None:
            logger.error("message cannot be None")
            yield {"type": "error", "content": "message cannot be None"}
            return
        if isinstance(message, str) and not message.strip():
            logger.error("message cannot be empty")
            yield {"type": "error", "content": "message cannot be empty"}
            return

        # Ensure ThreadManager exists (for direct agent usage without Agency)
        self._ensure_thread_manager()

        if self._thread_manager is None:
            logger.error(f"Agent '{self.name}' missing ThreadManager for streaming.")
            raise RuntimeError(f"Agent '{self.name}' missing ThreadManager.")

        # For direct agent usage, we need to ensure _agency_instance exists with minimal agents map
        if not self._agency_instance or not hasattr(self._agency_instance, "agents"):
            if sender_name is None:  # Direct user interaction without agency
                # Create a minimal agency-like object for compatibility
                class MinimalAgency:
                    def __init__(self, agent):
                        self.agents = {agent.name: agent}
                        self.user_context = {}

                self._agency_instance = MinimalAgency(self)
            else:
                raise RuntimeError(f"Agent '{self.name}' missing Agency instance for agent-to-agent communication.")

        # Generate a thread identifier based on communication context
        thread_id = self.get_thread_id(sender_name)
        logger.info(f"Agent '{self.name}' handling get_response_stream for thread: {thread_id}")
        thread = self._thread_manager.get_thread(thread_id)

        try:
            processed_initial_messages = ItemHelpers.input_to_new_input_list(message)
        except Exception as e:
            logger.error(f"Error processing input message for stream agent '{self.name}': {e}", exc_info=True)
            yield {"type": "error", "content": f"Invalid input message format: {e}"}
            return

        # Handle file attachments - support both old message_files and new file_ids
        files_to_attach = kwargs.get("file_ids") or kwargs.get("message_files")
        if files_to_attach and isinstance(files_to_attach, list):
            if kwargs.get("message_files"):
                warnings.warn(
                    "'message_files' parameter is deprecated. Use 'file_ids' instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            if processed_initial_messages:
                last_message = processed_initial_messages[-1]
                if isinstance(last_message, dict) and last_message.get("role") == "user":
                    current_content = last_message.get("content", "")
                    if isinstance(current_content, str):
                        content_list = [{"type": "input_text", "text": current_content}] if current_content else []
                    elif isinstance(current_content, list):
                        content_list = list(current_content)
                    else:
                        content_list = []
                    for file_id in files_to_attach:
                        if isinstance(file_id, str) and file_id.startswith("file-"):
                            file_content_item = {
                                "type": "input_file",
                                "file_id": file_id,
                            }
                            content_list.append(file_content_item)
                            logger.debug(f"Added file content item for file_id: {file_id}")
                        else:
                            logger.warning(f"Invalid file_id format: {file_id} for agent {self.name}")
                    last_message["content"] = content_list
                else:
                    logger.warning(f"Cannot attach files: Last message is not a user message for agent {self.name}")
            else:
                logger.warning(f"Cannot attach files: No messages to attach to for agent {self.name}")

        # --- Input history logic (match get_response) ---
        if sender_name is None:  # Top-level call from user or agency
            self._thread_manager.add_items_and_save(thread, processed_initial_messages)
            logger.debug(f"Added current message to shared thread {thread.thread_id} for top-level stream call.")
            history_for_runner = list(thread.items)  # Get full history after adding
        else:  # Agent-to-agent call (e.g., via SendMessage tool)
            history_up_to_this_call = list(thread.items)
            history_for_runner = history_up_to_this_call + processed_initial_messages
            logger.debug(
                f"Constructed temporary history for sub-agent '{self.name}' stream run. Shared thread not modified with this input."
            )

        # Sanitize tool_calls for OpenAI /v1/responses API compliance
        history_for_runner = self._sanitize_tool_calls_in_history(history_for_runner)

        try:
            master_context = self._prepare_master_context(context_override)
            hooks_to_use = hooks_override or self.hooks
            effective_run_config = run_config_override or RunConfig()
        except RuntimeError as e:
            logger.error(f"Error preparing context/hooks for stream agent '{self.name}': {e}", exc_info=True)
            raise e

        final_result_items = []
        try:
            logger.debug(f"Calling Runner.run_streamed for agent '{self.name}'...")
            result = Runner.run_streamed(
                starting_agent=self,
                input=history_for_runner,
                context=master_context,
                hooks=hooks_to_use,
                run_config=effective_run_config,
                max_turns=kwargs.get("max_turns", DEFAULT_MAX_TURNS),
            )
            async for event in result.stream_events():
                yield event
                if isinstance(event, RunItemStreamEvent):
                    final_result_items.append(event.item)
            logger.info(f"Runner.run_streamed completed for agent '{self.name}'.")

        except Exception as e:
            logger.error(f"Error during Runner.run_streamed for agent '{self.name}': {e}", exc_info=True)
            yield {"type": "error", "content": f"Runner execution failed: {e}"}
            return

        # After streaming, if it was a top-level call (user/agency direct call, not agent-to-agent),
        # and new items were generated by the run (captured in final_result_items),
        # these should be converted and saved to the thread to reflect the assistant's full turn.
        # Note: The `input` messages were already added above.
        # `final_result_items` here are `RunItem` objects from the stream.
        if sender_name is None and final_result_items:  # Top-level call and new items exist
            if self._thread_manager:
                items_to_save_from_stream: list[TResponseInputItem] = []
                logger.debug(
                    f"Preparing to save {len(final_result_items)} new items from stream result for agent '{self.name}' to thread {thread.thread_id}"
                )
                for i, run_item_obj in enumerate(final_result_items):
                    item_dict = self._run_item_to_tresponse_input_item(run_item_obj)
                    if item_dict:
                        is_duplicate = False
                        if processed_initial_messages:
                            if item_dict in processed_initial_messages and item_dict.get("role") == "user":
                                is_duplicate = True
                        if not is_duplicate:
                            items_to_save_from_stream.append(item_dict)
                            logger.debug(
                                f"  Stream Item {i + 1}/{len(final_result_items)} for agent '{self.name}' converted for saving: {item_dict.get('role')}"
                            )
                        else:
                            logger.debug(
                                f"  Stream Item {i + 1}/{len(final_result_items)} for agent '{self.name}' skipped as potential duplicate of input."
                            )
                    else:
                        logger.debug(
                            f"  Stream Item {i + 1}/{len(final_result_items)} for agent '{self.name}' ({type(run_item_obj).__name__}) skipped or failed conversion."
                        )
                if items_to_save_from_stream:
                    logger.info(
                        f"Saving {len(items_to_save_from_stream)} converted stream items for agent '{self.name}' to thread {thread.thread_id}"
                    )
                    self._thread_manager.add_items_and_save(thread, items_to_save_from_stream)

    # --- Helper Methods ---
    def get_thread_id(self, sender_name: str | None = None) -> str:
        """Construct a thread identifier based on sender and recipient names."""
        sender = sender_name or "user"
        return f"{sender}->{self.name}"

    def _run_item_to_tresponse_input_item(self, item: RunItem) -> TResponseInputItem | None:
        """Converts a RunItem from a RunResult into TResponseInputItem dictionary format for history.
        Returns None if the item type should not be directly added to history.
        """
        if isinstance(item, MessageOutputItem):
            content = ItemHelpers.text_message_output(item)
            logger.debug(f"Converting MessageOutputItem to history: role=assistant, content='{content[:50]}...'")
            return {"role": "assistant", "content": content}

        elif isinstance(item, ToolCallItem):
            tool_calls = []
            if hasattr(item, "raw_item"):
                raw = item.raw_item
                tool_call_id_for_array = None
                func_name = None
                func_args_str = None

                if isinstance(raw, ResponseFunctionToolCall):
                    # For /v1/responses API, use call_id for matching tool outputs
                    tool_call_id_for_array = getattr(raw, "call_id", None)
                    if tool_call_id_for_array is None:
                        # Fallback to id only if call_id is not available
                        tool_call_id_for_array = getattr(raw, "id", None)
                    func_name = getattr(raw, "name", None)
                    func_args_raw = getattr(raw, "arguments", None)
                    if not isinstance(func_args_raw, str):
                        try:
                            func_args_str = json.dumps(func_args_raw)
                        except TypeError as e:
                            logger.error(f"Could not serialize func_args for {func_name}: {func_args_raw}. Error: {e}")
                            return None
                    else:
                        func_args_str = func_args_raw
                elif isinstance(raw, ResponseFileSearchToolCall):
                    tool_call_id_for_array = getattr(raw, "id", None)
                    func_name = "FileSearch"  # Per agents.FileSearchTool.name
                    try:
                        func_args_str = json.dumps(
                            {
                                "queries": getattr(raw, "queries", []),
                                "results": [r.dict() for r in getattr(raw, "results", [])],
                            }
                        )
                    except TypeError as e:
                        logger.error(
                            f"Could not serialize queries for FileSearch: {getattr(raw, 'queries', [])}. Error: {e}"
                        )
                        return None
                else:
                    logger.warning(f"Unhandled raw_item type in ToolCallItem: {type(raw)}")
                    return None

                if not tool_call_id_for_array or not func_name:
                    logger.warning(
                        f"Converting ToolCallItem: Missing id or name. ID: {tool_call_id_for_array}, Name: {func_name}, Raw: {raw}"
                    )
                    return None

                tool_calls.append(
                    {
                        "id": tool_call_id_for_array,
                        "type": "function",
                        "function": {"name": func_name, "arguments": func_args_str},
                    }
                )
            else:
                logger.warning(f"ToolCallItem has no raw_item. Cannot convert: {item}")
                return None

            if tool_calls:
                logger.debug(f"Converted ToolCallItem to assistant message with tool_calls: {tool_calls}")
                return {"role": "assistant", "content": None, "tool_calls": tool_calls}
            else:
                logger.warning("ToolCallItem conversion resulted in no tool_calls.")
                return None

        elif isinstance(item, ToolCallOutputItem):
            tool_call_id = None
            output_content = str(item.output)

            # For /v1/responses API, prioritize call_id for matching tool outputs
            if hasattr(item, "tool_call_id") and item.tool_call_id:
                tool_call_id = item.tool_call_id
            elif isinstance(item.raw_item, ResponseFunctionToolCall):
                # ResponseFunctionToolCall from /v1/responses has 'call_id' for matching
                tool_call_id = getattr(item.raw_item, "call_id", None)
                if tool_call_id is None:  # Fallback only if call_id is not available
                    tool_call_id = getattr(item.raw_item, "id", None)
            elif isinstance(item.raw_item, dict) and "call_id" in item.raw_item:
                tool_call_id = item.raw_item.get("call_id")

            if tool_call_id:
                logger.debug(
                    f"Converting ToolCallOutputItem to assistant message: tool_call_id={tool_call_id}, content='{output_content[:50]}...'"
                )
                # Convert tool output to assistant message with tool_call_id in content
                return {
                    "role": "assistant",
                    "content": f"Tool output for call {tool_call_id}: {output_content}",
                }
            else:
                logger.warning(
                    f"Could not determine tool_call_id for ToolCallOutputItem: raw_item={item.raw_item}, item={item}"
                )
                return None

        else:
            logger.debug(f"Skipping RunItem type {type(item).__name__} for thread history saving.")
            return None

    def _prepare_master_context(self, context_override: dict[str, Any] | None) -> MasterContext:
        """Constructs the MasterContext for the current run."""
        if not self._agency_instance or not hasattr(self._agency_instance, "agents"):
            raise RuntimeError("Cannot prepare context: Agency instance or agents map missing.")
        if not self._thread_manager:
            raise RuntimeError("Cannot prepare context: ThreadManager missing.")

        # Start with base user context from agency, if it exists
        base_user_context = getattr(self._agency_instance, "user_context", {})
        merged_user_context = base_user_context.copy()
        if context_override:
            merged_user_context.update(context_override)

        return MasterContext(
            thread_manager=self._thread_manager,
            agents=self._agency_instance.agents,
            user_context=merged_user_context,
            current_agent_name=self.name,
        )

    def _validate_response(self, response_text: str) -> bool:
        """Internal helper to apply response validator if configured."""
        if self.response_validator:
            try:
                is_valid = self.response_validator(response_text)
                if not is_valid:
                    logger.warning(f"Response validation failed for agent {self.name}")
                return is_valid
            except Exception as e:
                logger.error(f"Error during response validation for agent {self.name}: {e}", exc_info=True)
                return False  # Treat validation errors as failure
        return True  # No validator means always valid

    @staticmethod
    def _sanitize_tool_calls_in_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Ensures only the most recent assistant message in the history has a 'tool_calls' field.
        Removes 'tool_calls' from all other messages.
        """
        # Find the index of the last assistant message
        last_assistant_idx = None
        for i in reversed(range(len(history))):
            if history[i].get("role") == "assistant":
                last_assistant_idx = i
                break
        if last_assistant_idx is None:
            return history
        # Remove 'tool_calls' from all assistant messages except the last one
        sanitized = []
        for idx, msg in enumerate(history):
            if msg.get("role") == "assistant" and "tool_calls" in msg and idx != last_assistant_idx:
                msg = dict(msg)
                msg.pop("tool_calls", None)
            sanitized.append(msg)
        return sanitized

    # --- Agency Configuration Methods --- (Called by Agency)
    def _set_thread_manager(self, manager: ThreadManager):
        """Allows the Agency to inject the ThreadManager instance."""
        self._thread_manager = manager

    def _set_agency_instance(self, agency: Any):
        """Allows the Agency to inject a reference to itself and its agent map."""
        if not hasattr(agency, "agents"):
            raise TypeError("Provided agency instance must have an 'agents' dictionary.")
        self._agency_instance = agency

    def _set_persistence_callbacks(
        self,
        load_threads_callback: Callable[[str], dict[str, Any] | None] | None = None,
        save_threads_callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        """Set persistence callbacks for the agent's thread manager.

        This method allows setting callbacks after agent initialization and will
        create a new ThreadManager with the provided callbacks if none exists.

        Args:
            load_threads_callback: Callback to load thread data by thread_id
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

    def _adapt_legacy_tool(self, legacy_tool: type[BaseTool]):
        """
        Adapts a legacy BaseTool (class-based) to a FunctionTool (function-based).
        Args:
            legacy_tool: A class inheriting from BaseTool.
        Returns:
            A FunctionTool instance.
        """
        name = legacy_tool.__name__
        description = legacy_tool.__doc__ or ""
        if bool(getattr(legacy_tool, "__abstractmethods__", set())):
            raise TypeError(f"Legacy tool '{name}' must implement all abstract methods.")
        if description == "":
            logger.warning(f"Warning: Tool {name} has no docstring.")
        # Use the Pydantic model schema for parameters
        params_json_schema = legacy_tool.model_json_schema()
        if legacy_tool.ToolConfig.strict:
            params_json_schema = ensure_strict_json_schema(params_json_schema)
        # Remove title/description at the top level, keep only in properties
        params_json_schema = {k: v for k, v in params_json_schema.items() if k not in ("title", "description")}
        params_json_schema["additionalProperties"] = False

        # The on_invoke_tool function
        async def on_invoke_tool(ctx, input_json: str):
            # Parse input_json to dict
            import json

            try:
                args = json.loads(input_json) if input_json else {}
            except Exception as e:
                return f"Error: Invalid JSON input: {e}"
            try:
                # Instantiate the legacy tool with args
                tool_instance = legacy_tool(**args)
                if inspect.iscoroutinefunction(tool_instance.run):
                    result = await tool_instance.run()
                else:
                    # Always run sync run() in a thread for async compatibility
                    result = await asyncio.to_thread(tool_instance.run)
                return str(result)
            except Exception as e:
                return f"Error running legacy tool: {e}"

        return FunctionTool(
            name=name,
            description=description.strip(),
            params_json_schema=params_json_schema,
            on_invoke_tool=on_invoke_tool,
            strict_json_schema=legacy_tool.ToolConfig.strict,
        )

    def _get_class_folder_path(self):
        try:
            # First, try to use the __file__ attribute of the module
            return os.path.abspath(os.path.dirname(self.__module__.__file__))
        except (TypeError, OSError, AttributeError):
            # If that fails, fall back to inspect
            try:
                class_file = inspect.getfile(self.__class__)
            except (TypeError, OSError, AttributeError):
                return "./"
            return os.path.abspath(os.path.realpath(os.path.dirname(class_file)))

    def get_class_folder_path(self):
        """Public method to get the class folder path."""
        try:
            # First, try to use the __file__ attribute of the module
            return os.path.abspath(os.path.dirname(self.__module__.__file__))
        except (TypeError, OSError, AttributeError):
            # If that fails, fall back to inspect
            try:
                class_file = inspect.getfile(self.__class__)
            except (TypeError, OSError, AttributeError):
                return "./"
            return os.path.abspath(os.path.realpath(os.path.dirname(class_file)))
