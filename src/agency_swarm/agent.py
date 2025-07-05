import asyncio
import importlib.util
import inspect
import json
import logging
import os
import sys
import warnings
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Any, TypeVar

from agents import (
    Agent as BaseAgent,
    InputGuardrailTripwireTriggered,
    ModelSettings,
    OutputGuardrailTripwireTriggered,
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
)
from agents.run import DEFAULT_MAX_TURNS
from agents.stream_events import RunItemStreamEvent
from agents.strict_schema import ensure_strict_json_schema
from agents.tool import FunctionTool
from openai import AsyncOpenAI, OpenAI
from openai.types.responses import ResponseFileSearchToolCall, ResponseFunctionWebSearch

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
        tools_folder (str | Path | None): Placeholder for future functionality to load tools from a directory.
        description (str | None): A description of the agent's role or purpose, used when generating
                                  dynamic `send_message` tools for other agents.
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
        _load_threads_callback (Callable[[], dict[str, Any]] | None): Callback to load all thread data.
        _save_threads_callback (Callable[[dict[str, Any]], None] | None): Callback to save all threads data.
    """

    # --- Agency Swarm Specific Parameters ---
    files_folder: str | Path | None
    tools_folder: str | Path | None  # Placeholder for future ToolFactory
    description: str | None
    output_type: type[Any] | None

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
        # --- Handle Deprecated Args ---
        deprecated_args_used = {}
        deprecated_model_settings = {}

        # Group deprecated model-related parameters
        model_related_params = [
            "temperature",
            "top_p",
            "max_completion_tokens",
            "max_prompt_tokens",
            "reasoning_effort",
            "truncation_strategy",
        ]

        for param in model_related_params:
            if param in kwargs:
                param_value = kwargs.pop(param)
                warnings.warn(
                    f"'{param}' is deprecated as a direct Agent parameter. Configure model settings via 'model_settings' parameter using a ModelSettings object from the agents SDK.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                deprecated_args_used[param] = param_value
                deprecated_model_settings[param] = param_value

        if "validation_attempts" in kwargs:
            val_attempts = kwargs.pop("validation_attempts")
            warnings.warn(
                "'validation_attempts' is deprecated.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["validation_attempts"] = val_attempts

        if "id" in kwargs:
            warnings.warn(
                "'id' parameter (OpenAI Assistant ID) is deprecated and no longer used for loading. Agent state is managed via PersistenceHooks.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["id"] = kwargs.pop("id")

        if "response_validator" in kwargs:
            warnings.warn(
                "'response_validator' parameter is deprecated. Use 'output_guardrails' and 'input_guardrails' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["response_validator"] = kwargs.pop("response_validator")

        if "tool_resources" in kwargs:
            warnings.warn(
                "'tool_resources' is deprecated. File resources should be managed via 'files_folder' and the 'upload_file' method for Vector Stores.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["tool_resources"] = kwargs.pop("tool_resources")

        if "file_ids" in kwargs:
            warnings.warn(
                "'file_ids' is deprecated. Use 'files_folder' to associate with Vector Stores or manage files via Agent methods.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["file_ids"] = kwargs.pop("file_ids")

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
            deprecated_args_used["examples"] = examples

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

        # Handle response_format parameter mapping to output_type
        if "response_format" in kwargs:
            response_format = kwargs.pop("response_format")
            if "output_type" not in kwargs or kwargs["output_type"] is None:
                kwargs["output_type"] = response_format
            warnings.warn(
                "'response_format' parameter is deprecated. Use 'output_type' instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            deprecated_args_used["response_format"] = response_format

        # Handle deprecated tools
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

        # Merge deprecated model settings into existing model_settings
        if deprecated_model_settings:
            existing_model_settings = kwargs.get("model_settings")

            # Handle existing model_settings being a ModelSettings instance or dict
            if isinstance(existing_model_settings, ModelSettings):
                # Convert ModelSettings to dict for merging
                existing_dict = existing_model_settings.to_json_dict()
            elif existing_model_settings is None:
                existing_dict = {}
            else:
                # Assume it's already a dict
                existing_dict = dict(existing_model_settings)

            # Create a new dict to avoid modifying the original
            merged_model_settings = dict(existing_dict)
            merged_model_settings.update(deprecated_model_settings)

            # to_json_dict returns None for keys that were not set
            keys_to_remove = [key for key, value in merged_model_settings.items() if value is None]
            for key in keys_to_remove:
                merged_model_settings.pop(key)

            # Resolve token setting conflicts
            self._resolve_token_settings(merged_model_settings, kwargs.get("name", "unknown"))

            # Create new ModelSettings instance from merged dict
            kwargs["model_settings"] = ModelSettings(**merged_model_settings)

            logger.info(
                f"Merged deprecated model settings into model_settings: {list(deprecated_model_settings.keys())}"
            )

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
        # Set description directly from current_agent_params, default to None if not provided
        self.description = current_agent_params.get("description")
        # output_type is handled by the base Agent constructor, no need to set it here

        # --- Persistence Callbacks ---
        self._load_threads_callback = current_agent_params.get("load_threads_callback")
        self._save_threads_callback = current_agent_params.get("save_threads_callback")

        # --- Internal State Init ---
        self._openai_client = None
        # Sync OpenAI client is lazily initialised when required
        self._openai_client_sync = None
        self._subagents = {}
        # _thread_manager and _agency_instance are injected by Agency

        self.file_manager = AgentFileManager(self)

        self.file_manager._parse_files_folder_for_vs_id()
        self._parse_schemas()
        self._load_tools_from_folder()

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
        if any(getattr(t, "name", None) == getattr(tool, "name", None) for t in self.tools):
            logger.warning(
                f"Tool with name '{getattr(tool, 'name', '(unknown)')}' already exists for agent "
                f"'{self.name}'. Skipping."
            )
            return

        if not isinstance(tool, Tool):
            raise TypeError(f"Expected an instance of Tool, got {type(tool)}")

        self.tools.append(tool)
        logger.debug(f"Tool '{getattr(tool, 'name', '(unknown)')}' added to agent '{self.name}'")

    def _load_tools_from_folder(self) -> None:
        """Load tools defined in ``tools_folder`` and add them to the agent.

        Supports both legacy ``BaseTool`` subclasses and ``FunctionTool``
        instances created via the ``@function_tool`` decorator. This restores the
        automatic discovery behavior from Agency Swarm v0.x while also handling
        the new function-based tools.
        """

        if not self.tools_folder:
            return

        folder_path = Path(self.tools_folder)
        if not folder_path.is_absolute():
            folder_path = Path(self._get_class_folder_path()) / folder_path

        if not folder_path.is_dir():
            logger.warning("Tools folder path is not a directory. Skipping... %s", folder_path)
            return

        for file in folder_path.iterdir():
            if not file.is_file() or file.suffix != ".py" or file.name.startswith("_"):
                continue

            module_name = file.stem
            try:
                spec = importlib.util.spec_from_file_location(module_name, file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[f"{module_name}_{id(self)}"] = module
                    spec.loader.exec_module(module)
                else:
                    logger.error("Unable to import tool module %s", file)
                    continue
            except Exception as e:
                logger.error("Error importing tool module %s: %s", file, e)
                continue

            # Legacy BaseTool: expect class with same name as file
            legacy_class = getattr(module, module_name, None)
            if inspect.isclass(legacy_class) and issubclass(legacy_class, BaseTool) and legacy_class is not BaseTool:
                try:
                    tool = self._adapt_legacy_tool(legacy_class)
                    self.add_tool(tool)
                except Exception as e:
                    logger.error("Error adapting tool %s: %s", module_name, e)

            # FunctionTool instances defined in the module
            for obj in module.__dict__.values():
                if isinstance(obj, FunctionTool):
                    try:
                        self.add_tool(obj)
                    except Exception as e:
                        logger.error("Error adding function tool from %s: %s", file, e)

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
                f"Expected an instance of Agent, got {type(recipient_agent)}. "
                f"Ensure agents are initialized before registration."
            )
        if not hasattr(recipient_agent, "name") or not isinstance(recipient_agent.name, str):
            raise TypeError("Recipient agent must have a 'name' attribute of type str.")

        recipient_name = recipient_agent.name

        # Prevent an agent from registering itself as a subagent
        if recipient_name == self.name:
            raise ValueError("Agent cannot register itself as a subagent.")

        # Initialize _subagents if it doesn't exist
        if not hasattr(self, "_subagents") or self._subagents is None:
            self._subagents = {}

        if recipient_name in self._subagents:
            logger.warning(
                f"Agent '{recipient_name}' is already registered as a subagent for '{self.name}'. "
                f"Skipping tool creation."
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
        additional_instructions: str | None = None,  # New parameter for v1.x
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
        logger.info(f"Agent '{self.name}' starting run.")
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

        # Store original instructions for restoration
        original_instructions = self.instructions

        # Temporarily modify instructions if additional_instructions provided
        if additional_instructions:
            if not isinstance(additional_instructions, str):
                raise ValueError("additional_instructions must be a string")
            logger.debug(
                f"Appending additional instructions to agent '{self.name}': {additional_instructions[:100]}..."
            )
            if self.instructions:
                self.instructions = self.instructions + "\n\n" + additional_instructions
            else:
                self.instructions = additional_instructions

        try:
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

                        file_content_items = self.file_manager.sort_file_attachments(files_to_attach)
                        content_list.extend(file_content_items)

                        # Update the message content
                        if content_list != []:
                            last_message["content"] = content_list
                    else:
                        logger.warning(f"Cannot attach files: Last message is not a user message for agent {self.name}")
                else:
                    logger.warning(f"Cannot attach files: No messages to attach to for agent {self.name}")

            history_for_runner: list[TResponseInputItem]
            # Always save current message items to thread (both user and agent-to-agent calls)
            self._thread_manager.add_items_and_save(thread, processed_current_message_items)
            logger.debug(f"Added current message to thread {thread.thread_id}.")
            history_for_runner = list(thread.items)  # Get full history after adding

            # The history_for_runner now contains OpenAI-compatible message dictionaries.
            # It should include user, assistant (possibly with tool_calls), and tool messages if they are part of the conversation.
            # No filtering is applied here based on user instruction.

            history_for_runner = self._sanitize_tool_calls_in_history(history_for_runner)
            history_for_runner = self._ensure_tool_calls_content_safety(history_for_runner)
            logger.debug(f"Running agent '{self.name}' for thread '{thread_id}' (length {len(history_for_runner)}):")
            for i, m in enumerate(history_for_runner):
                content_preview = str(m.get("content", ""))[:70] if m.get("content") else ""
                tool_calls_preview = str(m.get("tool_calls", ""))[:70] if m.get("tool_calls") else ""
                logger.debug(
                    f"  [History #{i}] role={m.get('role')}, content='{content_preview}...', "
                    f"tool_calls='{tool_calls_preview}...'"
                )

            try:
                logger.debug(
                    f"Calling Runner.run for agent '{self.name}' with {len(history_for_runner)} history items."
                )
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

            except OutputGuardrailTripwireTriggered as e:
                logger.warning(f"OutputGuardrailTripwireTriggered for agent '{self.name}': {e}", exc_info=True)
                raise e

            except InputGuardrailTripwireTriggered as e:
                logger.warning(f"InputGuardrailTripwireTriggered for agent '{self.name}': {e}", exc_info=True)
                raise e

            except Exception as e:
                logger.error(f"Error during Runner.run for agent '{self.name}': {e}", exc_info=True)
                raise AgentsException(f"Runner execution failed for agent {self.name}") from e

            # Always save response items to thread (both user and agent-to-agent calls)
            if self._thread_manager and run_result.new_items:
                thread = self._thread_manager.get_thread(thread_id)
                items_to_save: list[TResponseInputItem] = []
                logger.debug(
                    f"Preparing to save {len(run_result.new_items)} new items from RunResult to thread {thread.thread_id}"
                )

                # Only extract hosted tool results if hosted tools were actually used
                hosted_tool_outputs = self._extract_hosted_tool_results_if_needed(run_result.new_items)

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

                # Add synthetic hosted tool outputs to the conversation history
                if hosted_tool_outputs:
                    items_to_save.extend(hosted_tool_outputs)
                    logger.info(
                        f"Added {len(hosted_tool_outputs)} synthetic hosted tool output items to preserve results"
                    )

                if items_to_save:
                    logger.info(f"Saving {len(items_to_save)} converted RunResult items to thread {thread.thread_id}")
                    self._thread_manager.add_items_and_save(thread, items_to_save)

            return run_result

        finally:
            # Always restore original instructions
            self.instructions = original_instructions
            if additional_instructions:
                logger.debug(f"Restored original instructions for agent '{self.name}'")

    async def get_response_stream(
        self,
        message: str | list[dict[str, Any]],
        sender_name: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        additional_instructions: str | None = None,  # New parameter for v1.x
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

        # Store original instructions for restoration
        original_instructions = self.instructions

        # Temporarily modify instructions if additional_instructions provided
        if additional_instructions:
            if not isinstance(additional_instructions, str):
                raise ValueError("additional_instructions must be a string")
            logger.debug(
                f"Appending additional instructions to agent '{self.name}' for streaming: "
                f"{additional_instructions[:100]}..."
            )
            if self.instructions:
                self.instructions = self.instructions + "\n\n" + additional_instructions
            else:
                self.instructions = additional_instructions

        try:
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

                        file_content_items = self.file_manager.sort_file_attachments(files_to_attach)
                        content_list.extend(file_content_items)

                        if content_list != []:
                            last_message["content"] = content_list
                    else:
                        logger.warning(f"Cannot attach files: Last message is not a user message for agent {self.name}")
                else:
                    logger.warning(f"Cannot attach files: No messages to attach to for agent {self.name}")

            # --- Input history logic (match get_response) ---
            # Always save current message items to thread (both user and agent-to-agent calls)
            self._thread_manager.add_items_and_save(thread, processed_initial_messages)
            logger.debug(f"Added current message to thread {thread.thread_id} for stream call.")
            history_for_runner = list(thread.items)  # Get full history after adding

            # Sanitize tool_calls for OpenAI /v1/responses API compliance
            history_for_runner = self._sanitize_tool_calls_in_history(history_for_runner)

            # Additional safety: ensure no null content for messages with tool_calls
            history_for_runner = self._ensure_tool_calls_content_safety(history_for_runner)

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
                    # Collect RunItems from the stream events if needed
                    if isinstance(event, RunItemStreamEvent):
                        final_result_items.append(event.item)
                logger.info(f"Runner.run_streamed completed for agent '{self.name}'.")

            except Exception as e:
                logger.error(f"Error during Runner.run_streamed for agent '{self.name}': {e}", exc_info=True)
                yield {"type": "error", "content": f"Runner execution failed: {e}"}
                return

            # After streaming, if new items were generated by the run (captured in final_result_items),
            # these should be converted and saved to the thread to reflect the assistant's full turn.
            # Note: The `input` messages were already added above.
            # `final_result_items` here are `RunItem` objects from the stream.
            if final_result_items:  # New items exist
                if self._thread_manager:
                    items_to_save_from_stream: list[TResponseInputItem] = []
                    logger.debug(
                        f"Preparing to save {len(final_result_items)} new items from stream result for agent "
                        f"'{self.name}' to thread {thread.thread_id}"
                    )

                    # Only extract hosted tool results if hosted tools were actually used
                    hosted_tool_outputs = self._extract_hosted_tool_results_if_needed(final_result_items)

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

                    # Add synthetic hosted tool outputs to the conversation history
                    if hosted_tool_outputs:
                        items_to_save_from_stream.extend(hosted_tool_outputs)
                        logger.info(
                            f"Added {len(hosted_tool_outputs)} synthetic hosted tool output items to preserve results"
                        )

                    if items_to_save_from_stream:
                        logger.info(
                            f"Saving {len(items_to_save_from_stream)} converted stream items for agent '{self.name}' to thread {thread.thread_id}"
                        )
                        self._thread_manager.add_items_and_save(thread, items_to_save_from_stream)

        finally:
            # Always restore original instructions
            self.instructions = original_instructions
            if additional_instructions:
                logger.debug(f"Restored original instructions for agent '{self.name}' after streaming")

    # --- Helper Methods ---
    def get_thread_id(self, sender_name: str | None = None) -> str:
        """Construct a thread identifier based on sender and recipient names."""
        sender = sender_name or "user"
        return f"{sender}->{self.name}"

    def _run_item_to_tresponse_input_item(self, item: RunItem) -> TResponseInputItem | None:
        """Converts a RunItem from a RunResult into TResponseInputItem dictionary format for history.
        Uses the SDK's built-in to_input_item() method for proper conversion.
        Returns None if the item should not be directly added to history.
        """
        try:
            # Use the SDK's built-in conversion method instead of manual conversion
            # This fixes the critical bug where ToolCallOutputItem was incorrectly converted
            # to assistant messages instead of proper function call output format
            converted_item = item.to_input_item()

            logger.debug(f"Converting {type(item).__name__} using SDK to_input_item(): {converted_item}")
            return converted_item

        except Exception as e:
            logger.warning(f"Failed to convert {type(item).__name__} using to_input_item(): {e}")
            return None

    def _extract_hosted_tool_results_if_needed(self, run_items: list[RunItem]) -> list[TResponseInputItem]:
        """
        Optimized version that only extracts hosted tool results if hosted tools were actually used.
        This prevents expensive parsing on every response when no hosted tools exist.
        """
        # Quick check: do we have any hosted tool calls?
        has_hosted_tools = any(
            isinstance(item, ToolCallItem)
            and isinstance(item.raw_item, ResponseFileSearchToolCall | ResponseFunctionWebSearch)
            for item in run_items
        )

        if not has_hosted_tools:
            return []  # Early exit - no hosted tools used

        return self._extract_hosted_tool_results(run_items)

    def _extract_hosted_tool_results(self, run_items: list[RunItem]) -> list[TResponseInputItem]:
        """
        Extract hosted tool results (FileSearch, WebSearch) from assistant message content
        and create special assistant messages to preserve results in conversation history.
        """
        synthetic_outputs = []

        # Find hosted tool calls and assistant messages
        hosted_tool_calls = []
        assistant_messages = []

        for item in run_items:
            if isinstance(item, ToolCallItem):
                if isinstance(item.raw_item, ResponseFileSearchToolCall | ResponseFunctionWebSearch):
                    hosted_tool_calls.append(item)
            elif isinstance(item, MessageOutputItem):
                assistant_messages.append(item)

        # Extract results for each hosted tool call
        for tool_call_item in hosted_tool_calls:
            tool_call = tool_call_item.raw_item

            # Create preservation message based on tool type
            if isinstance(tool_call, ResponseFileSearchToolCall):
                preservation_content = (
                    f"[TOOL_RESULT_PRESERVATION] Tool Call ID: {tool_call.id}\nTool Type: file_search\n"
                )

                file_count = 0

                # First: try direct results from tool call (most complete)
                if hasattr(tool_call, "results") and tool_call.results:
                    for result in tool_call.results:
                        file_count += 1
                        file_id = getattr(result, "file_id", "unknown")
                        # Capture FULL content (not truncated to 200 chars)
                        content_text = getattr(result, "text", "")
                        preservation_content += f"File {file_count}: {file_id}\nContent: {content_text}\n\n"

                # Fallback: parse assistant messages for annotations
                if file_count == 0:
                    for msg_item in assistant_messages:
                        message = msg_item.raw_item
                        if hasattr(message, "content") and message.content:
                            for content_item in message.content:
                                if hasattr(content_item, "annotations") and content_item.annotations:
                                    for annotation in content_item.annotations:
                                        if hasattr(annotation, "type") and annotation.type == "file_citation":
                                            file_count += 1
                                            file_id = getattr(annotation, "file_id", "unknown")
                                            # Capture FULL content (not truncated to 200 chars)
                                            content_text = getattr(content_item, "text", "")
                                            preservation_content += (
                                                f"File {file_count}: {file_id}\nContent: {content_text}\n\n"
                                            )

                if file_count > 0:
                    synthetic_outputs.append({"role": "assistant", "content": preservation_content})
                    logger.debug(f"Created file_search preservation message for call_id: {tool_call.id}")

            elif isinstance(tool_call, ResponseFunctionWebSearch):
                preservation_content = (
                    f"[TOOL_RESULT_PRESERVATION] Tool Call ID: {tool_call.id}\nTool Type: web_search\n"
                )

                # Capture FULL search results (not truncated to 500 chars)
                for msg_item in assistant_messages:
                    message = msg_item.raw_item
                    if hasattr(message, "content") and message.content:
                        for content_item in message.content:
                            if hasattr(content_item, "text") and content_item.text:
                                preservation_content += f"Search Results:\n{content_item.text}\n"
                                synthetic_outputs.append({"role": "assistant", "content": preservation_content})
                                logger.debug(f"Created web_search preservation message for call_id: {tool_call.id}")
                                break

        return synthetic_outputs

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

    # _validate_response removed - use output_guardrails instead

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

    @staticmethod
    def _ensure_tool_calls_content_safety(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Ensures that assistant messages with tool_calls have non-null content.
        This prevents OpenAI API errors when switching between sync and streaming modes.
        """
        sanitized = []
        for msg in history:
            if msg.get("role") == "assistant" and msg.get("tool_calls") and msg.get("content") is None:
                # Create a copy to avoid modifying the original
                msg = dict(msg)
                # Generate descriptive content for tool calls
                tool_descriptions = []
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict):
                        func_name = tc.get("function", {}).get("name", "unknown")
                        tool_descriptions.append(func_name)

                if tool_descriptions:
                    msg["content"] = f"Using tools: {', '.join(tool_descriptions)}"
                else:
                    msg["content"] = "Executing tool calls"

                logger.debug(f"Fixed null content for assistant message with tool calls: {msg.get('content')}")

            sanitized.append(msg)
        return sanitized

    @staticmethod
    def _resolve_token_settings(model_settings_dict: dict[str, Any], agent_name: str = "unknown") -> None:
        """
        Resolves conflicts between max_tokens, max_prompt_tokens, and max_completion_tokens.

        Args:
            model_settings_dict: Dictionary of model settings to modify in place
            agent_name: Name of the agent for logging purposes
        """
        has_max_tokens = "max_tokens" in model_settings_dict
        has_max_prompt_tokens = "max_prompt_tokens" in model_settings_dict
        has_max_completion_tokens = "max_completion_tokens" in model_settings_dict

        # Since oai only kept 1 parameter to manage tokens, write one of the existing parameters to max_tokens
        if has_max_tokens:
            # If max_tokens is specified, drop prompt and completion tokens
            if has_max_prompt_tokens or has_max_completion_tokens:
                logger.info(
                    f"max_tokens is specified, ignoring max_prompt_tokens and max_completion_tokens for agent '{agent_name}'"
                )
                model_settings_dict.pop("max_prompt_tokens", None)
                model_settings_dict.pop("max_completion_tokens", None)
        else:
            # If max_tokens is not specified, handle prompt/completion tokens
            if has_max_prompt_tokens and has_max_completion_tokens:
                # Both are present, prefer completion tokens and warn
                model_settings_dict["max_tokens"] = model_settings_dict["max_completion_tokens"]
                model_settings_dict.pop("max_prompt_tokens", None)
                model_settings_dict.pop("max_completion_tokens", None)
                logger.warning(
                    f"Both max_prompt_tokens and max_completion_tokens specified for agent '{agent_name}'. "
                    f"Using max_completion_tokens value ({model_settings_dict['max_tokens']}) for max_tokens and ignoring max_prompt_tokens."
                )
            elif has_max_completion_tokens:
                # Only completion tokens present
                model_settings_dict["max_tokens"] = model_settings_dict["max_completion_tokens"]
                model_settings_dict.pop("max_completion_tokens", None)
            elif has_max_prompt_tokens:
                # Only prompt tokens present
                model_settings_dict["max_tokens"] = model_settings_dict["max_prompt_tokens"]
                model_settings_dict.pop("max_prompt_tokens", None)

        return model_settings_dict

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
