import inspect
import json
import logging
import re
import shutil
import uuid
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
from openai import AsyncOpenAI, NotFoundError
from openai.types.responses import ResponseFunctionToolCall

from .context import MasterContext
from .thread import ThreadManager
from .tools.send_message import SendMessage

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
        _thread_manager (ThreadManager | None): Internal reference to the agency's `ThreadManager`.
                                                Set by the parent `Agency`.
        _agency_instance (Any | None): Internal reference to the parent `Agency` instance. Set by the parent `Agency`.
        _associated_vector_store_id (str | None): The ID of the OpenAI Vector Store associated via `files_folder`.
        files_folder_path (Path | None): The resolved absolute path for `files_folder`.
        _subagents (dict[str, "Agent"]): Dictionary mapping names of registered subagents to their instances.
    """

    # --- Agency Swarm Specific Parameters ---
    files_folder: str | Path | None
    tools_folder: str | Path | None  # Placeholder for future ToolFactory
    description: str | None
    response_validator: Callable[[str], bool] | None

    # --- Internal State ---
    _thread_manager: ThreadManager | None = None
    _agency_instance: Any | None = None  # Holds reference to parent Agency
    _associated_vector_store_id: str | None = None
    files_folder_path: Path | None = None
    _subagents: dict[str, "Agent"]

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
                      `response_validator`). Deprecated parameters are handled with warnings.

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
            deprecated_args_used["schemas_folder"] = kwargs.pop("schemas_folder", None)
            deprecated_args_used["api_headers"] = kwargs.pop("api_headers", None)
            deprecated_args_used["api_params"] = kwargs.pop("api_params", None)
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
            elif key in {"files_folder", "tools_folder", "response_validator", "description"}:
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
        self.response_validator = current_agent_params.get("response_validator")
        # Set description directly from current_agent_params, default to None if not provided
        self.description = current_agent_params.get("description")

        # --- Internal State Init ---
        self._subagents = {}
        # _thread_manager and _agency_instance are injected by Agency

        # --- Setup ---
        self._load_tools_from_folder()  # Placeholder call
        self._init_file_handling()

    # --- Properties ---
    @property
    def client(self) -> AsyncOpenAI:
        """Provides access to an initialized AsyncOpenAI client instance."""
        # Consider making client management more robust if needed
        if not hasattr(self, "_openai_client"):
            self._openai_client = AsyncOpenAI()
        return self._openai_client

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
    def _init_file_handling(self) -> None:
        """Initializes file handling: sets up local folder and VS ID if specified."""
        self._associated_vector_store_id = None
        self.files_folder_path = None
        if not self.files_folder:
            return

        try:
            self.files_folder_path = Path(self.files_folder).resolve()
            folder_name = self.files_folder_path.name
            match = re.search(r"_vs_([a-zA-Z0-9\-]+)$", folder_name)
            if match:
                vs_id = match.group(1)
                logger.info(f"Detected Vector Store ID '{vs_id}' in files_folder name.")
                self._associated_vector_store_id = vs_id
                base_folder_name = folder_name[: match.start()]
                # Construct the base path
                base_path = self.files_folder_path.parent / base_folder_name
                # Create the base directory
                base_path.mkdir(parents=True, exist_ok=True)
                # Assign the corrected base path
                self.files_folder_path = base_path
            else:
                # If no VS ID, just ensure the original path exists
                self.files_folder_path.mkdir(parents=True, exist_ok=True)

            # This log message should now show the correct path
            logger.info(f"Agent '{self.name}' local files folder: {self.files_folder_path}")

            if self._associated_vector_store_id:
                self._ensure_file_search_tool()
        except Exception as e:
            logger.error(
                f"Error initializing file handling for path '{self.files_folder}': {e}",
                exc_info=True,
            )
            self.files_folder_path = None  # Reset on error

    def _ensure_file_search_tool(self):
        """Adds or updates the FileSearchTool if a VS ID is associated."""
        if not self._associated_vector_store_id:
            return
        # Remove existing FileSearchTool(s) first to avoid duplicates/conflicts
        self.tools = [t for t in self.tools if not isinstance(t, FileSearchTool)]
        logger.info(f"Adding FileSearchTool for VS ID: {self._associated_vector_store_id}")
        self.add_tool(FileSearchTool(vector_store_ids=[self._associated_vector_store_id]))

    async def upload_file(self, file_path: str) -> str:
        """
        Uploads a file to OpenAI and potentially copies it locally and associates it with a Vector Store.

        - Copies the file to the agent's `files_folder` if specified.
        - Uploads the file to OpenAI with purpose "assistants".
        - If `files_folder` is associated with a Vector Store (e.g., `path/to/folder_vs_abc123`),
          the uploaded OpenAI file is added to that Vector Store.
        - Ensures the `FileSearchTool` is added/updated if a Vector Store is associated.

        Args:
            file_path (str): The path to the local file to upload.

        Returns:
            str: The OpenAI File ID of the uploaded file.

        Raises:
            FileNotFoundError: If the `file_path` does not exist or is not a file.
            AgentsException: If the upload to OpenAI fails or association with the Vector Store fails.
        """
        source_path = Path(file_path)
        if not source_path.is_file():
            raise FileNotFoundError(f"Source file not found: {file_path}")

        local_upload_path = source_path  # Default to source if no local copy needed

        # Copy locally if folder is set
        if self.files_folder_path:
            # Simple copy, overwrites allowed for simplicity now.
            # Could add UUID or checks if needed.
            local_destination = self.files_folder_path / source_path.name
            try:
                shutil.copy2(source_path, local_destination)
                logger.info(f"Copied file locally to {local_destination}")
                local_upload_path = local_destination
            except Exception as e:
                logger.error(f"Error copying file {source_path} locally: {e}", exc_info=True)
                # Continue with original path for OpenAI upload

        # Upload to OpenAI
        try:
            logger.info(f"Uploading file '{local_upload_path.name}' to OpenAI...")
            openai_file = await self.client.files.create(file=local_upload_path.open("rb"), purpose="assistants")
            logger.info(f"Uploaded to OpenAI. File ID: {openai_file.id}")

            # Associate with Vector Store if needed
            if self._associated_vector_store_id:
                try:
                    logger.info(f"Adding OpenAI file {openai_file.id} to VS {self._associated_vector_store_id}")
                    # Check if file already exists in VS (optional, API call)
                    # vs_files = await self.client.beta.vector_stores.files.list(vector_store_id=self._associated_vector_store_id, limit=100)
                    # if any(f.id == openai_file.id for f in vs_files.data):
                    #     logger.debug(f"File {openai_file.id} already in VS {self._associated_vector_store_id}.")
                    # else:
                    await self.client.beta.vector_stores.files.create(
                        vector_store_id=self._associated_vector_store_id, file_id=openai_file.id
                    )
                    logger.info(f"Added file {openai_file.id} to VS {self._associated_vector_store_id}.")
                    self._ensure_file_search_tool()  # Ensure tool is present after adding first file
                except NotFoundError:
                    logger.error(
                        f"Vector Store {self._associated_vector_store_id} not found when adding file {openai_file.id}."
                    )
                except Exception as e:
                    logger.error(
                        f"Error adding file {openai_file.id} to VS {self._associated_vector_store_id}: {e}",
                        exc_info=True,
                    )

            return openai_file.id

        except Exception as e:
            logger.error(f"Error uploading file {local_upload_path.name} to OpenAI: {e}", exc_info=True)
            raise AgentsException(f"Failed to upload file to OpenAI: {e}") from e

    async def check_file_exists(self, file_path: str) -> str | None:
        """
        Checks if a file with the same name exists in the agent's associated Vector Store (if any).

        Args:
            file_path (str): The path or name of the file to check. Only the filename is used for matching.

        Returns:
            str | None: The OpenAI File ID if a matching file is found in the Vector Store, otherwise None.
                         Returns None if the agent has no associated Vector Store.
        """
        if not self._associated_vector_store_id:
            return None
        target_filename = Path(file_path).name
        try:
            logger.debug(f"Checking for file '{target_filename}' in VS {self._associated_vector_store_id}...")
            vs_files_page = await self.client.beta.vector_stores.files.list(
                vector_store_id=self._associated_vector_store_id, limit=100
            )
            for vs_file in vs_files_page.data:
                try:
                    file_object = await self.client.files.retrieve(vs_file.id)
                    if file_object.filename == target_filename:
                        logger.debug(f"Found matching file in VS: {vs_file.id}")
                        return vs_file.id
                except NotFoundError:
                    logger.warning(f"VS file {vs_file.id} not found in OpenAI files.")
                except Exception as e_inner:
                    logger.warning(f"Error retrieving details for file {vs_file.id}: {e_inner}")
            return None
        except NotFoundError:
            logger.error(f"Vector Store {self._associated_vector_store_id} not found during file check.")
            return None
        except Exception as e:
            logger.error(
                f"Error checking file existence in VS {self._associated_vector_store_id}: {e}",
                exc_info=True,
            )
            return None

    # --- Core Execution Methods ---
    async def get_response(
        self,
        message: str | list[dict[str, Any]],
        sender_name: str | None = None,
        chat_id: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config: RunConfig | None = None,
        **kwargs: Any,
    ) -> RunResult:
        """
        Runs the agent's turn using the `agents.Runner`, returning the full execution result.

        This is the primary method for interacting with an agent. It handles retrieving
        or creating the conversation thread, preparing context and hooks, executing
        the agent's logic via the `Runner`, optionally validating the response, and
        saving results to the thread if it's a top-level call (not agent-to-agent).

        Args:
            message (str | list[dict[str, Any]]): The input message for the agent. Can be a simple
                                                  string or a list of OpenAI-compatible message dicts.
            sender_name (str | None, optional): The name of the sending agent if this is an
                                                agent-to-agent message. Defaults to None (indicating
                                                user interaction).
            chat_id (str | None, optional): The ID of the conversation thread to use. If None, a new
                                            chat ID is generated for user interactions. Required for
                                            agent-to-agent messages initiated via tool calls.
            context_override (dict[str, Any] | None, optional): Additional user context to merge into
                                                               the `MasterContext` for this run.
            hooks_override (RunHooks | None, optional): Custom `RunHooks` to use for this specific run,
                                                       overriding the agent's default hooks.
            run_config (RunConfig | None, optional): Configuration options for the `agents.Runner`.
            **kwargs: Additional keyword arguments passed directly to `agents.Runner.run` (e.g., `max_turns`).

        Returns:
            RunResult: An object containing the full details of the agent run, including all generated
                       items (messages, tool calls, outputs) and the final output.

        Raises:
            RuntimeError: If the agent has not been properly configured with a `ThreadManager`
                          or associated with an `Agency` instance before being called.
            ValueError: If `sender_name` is provided (agent-to-agent call) but `chat_id` is missing.
            AgentsException: If an error occurs during the `agents.Runner` execution.
        """
        # 1. Validate Prerequisites & Get Thread
        if not self._thread_manager:
            raise RuntimeError(f"Agent '{self.name}' missing ThreadManager.")
        if not self._agency_instance or not hasattr(self._agency_instance, "agents"):
            raise RuntimeError(f"Agent '{self.name}' missing Agency instance or agents map.")

        # Determine chat_id if not provided (e.g., for user interaction)
        effective_chat_id = chat_id
        if sender_name is None and not effective_chat_id:
            effective_chat_id = f"chat_{uuid.uuid4()}"
            logger.info(f"New user interaction, generated chat_id: {effective_chat_id}")
        elif sender_name is not None and not effective_chat_id:
            # This case should be prevented by the check below, but handle defensively
            raise ValueError("chat_id is required for agent-to-agent communication within get_response.")

        logger.info(f"Agent '{self.name}' handling get_response for chat_id: {effective_chat_id}")
        thread = self._thread_manager.get_thread(effective_chat_id)

        # Add user message to thread before run
        if sender_name is None:  # Only add if it's initial user input
            try:
                items_to_add = ItemHelpers.input_to_new_input_list(message)
                thread.add_items(items_to_add)
                logger.debug(f"Added initial user message to thread {thread.thread_id} before run.")
            except Exception as e:
                logger.error(f"Error processing initial input message for get_response: {e}", exc_info=True)

        # 3. Prepare Context (History is handled internally by Runner now)
        # history_for_runner = thread.get_history() # Don't need to get history here
        master_context = self._prepare_master_context(context_override, effective_chat_id)

        # 4. Prepare Hooks & Config
        hooks_to_use = hooks_override or self.hooks
        effective_run_config = run_config or RunConfig()

        # 5. Execute via Runner
        try:
            logger.debug(f"Calling Runner.run for agent '{self.name}'...")
            # Call Runner.run as a class method, passing the initial input
            run_result: RunResult = await Runner.run(
                starting_agent=self,
                input=thread.items,  # Runner handles adding this initial input
                context=master_context,
                hooks=hooks_to_use,
                run_config=effective_run_config,
                max_turns=kwargs.get("max_turns", DEFAULT_MAX_TURNS),
                previous_response_id=kwargs.get("previous_response_id"),
            )
            # Log completion based on presence of final_output
            completion_info = (
                f"Output Type: {type(run_result.final_output).__name__}"
                if run_result.final_output is not None
                else "No final output"
            )
            logger.info(f"Runner.run completed for agent '{self.name}'. {completion_info}")

        except Exception as e:
            logger.error(f"Error during Runner.run for agent '{self.name}': {e}", exc_info=True)
            raise AgentsException(f"Runner execution failed for agent {self.name}") from e

        # 6. Optional: Validate Response
        response_text_for_validation = ""
        if run_result.new_items:
            # Use ItemHelpers to extract text from message output items in the result
            response_text_for_validation = ItemHelpers.text_message_outputs(run_result.new_items)

        if response_text_for_validation and self.response_validator:
            if not self._validate_response(response_text_for_validation):
                logger.warning(f"Response validation failed for agent '{self.name}'")

        # 7. Add final result items to thread ONLY if it's a top-level call (from user/agency)
        if sender_name is None:
            if self._thread_manager and run_result.new_items:
                thread = self._thread_manager.get_thread(effective_chat_id)
                items_to_save: list[TResponseInputItem] = []
                logger.debug(f"Preparing to save {len(run_result.new_items)} new items to thread {thread.thread_id}")
                for i, run_item in enumerate(run_result.new_items):
                    item_dict = self._run_item_to_tresponse_input_item(run_item)
                    if item_dict:
                        items_to_save.append(item_dict)
                        logger.debug(f"  Item {i + 1}/{len(run_result.new_items)} converted for saving: {item_dict}")
                    else:
                        logger.debug(
                            f"  Item {i + 1}/{len(run_result.new_items)} ({type(run_item).__name__}) skipped or failed conversion."
                        )

                if items_to_save:
                    logger.info(f"Saving {len(items_to_save)} converted items to thread {thread.thread_id}")
                    self._thread_manager.add_items_and_save(thread, items_to_save)

        # 8. Return Result
        return run_result

    async def get_response_stream(
        self,
        message: str | list[dict[str, Any]],
        sender_name: str | None = None,
        chat_id: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:
        """
        Runs the agent's turn using the `agents.Runner` in streaming mode.

        Yields events as they occur during the agent's execution (e.g., tool calls,
        text generation deltas). Handles context, hooks, and thread management similarly
        to `get_response`.

        Args:
            message (str | list[dict[str, Any]]): The input message for the agent.
            sender_name (str | None, optional): The name of the sending agent, if applicable.
            chat_id (str | None, optional): The ID of the conversation thread. If None for user
                                            interaction, a new one is generated. Required for agent-to-agent calls.
            context_override (dict[str, Any] | None, optional): Additional user context.
            hooks_override (RunHooks | None, optional): Custom `RunHooks` for this run.
            run_config_override (RunConfig | None, optional): Custom `RunConfig` for this run.
            **kwargs: Additional arguments passed to `agents.Runner.run_streamed`.

        Yields:
            Any: Events generated by the `agents.Runner.run_streamed` execution, such as
                 `RunItemStreamEvent`, `TextStreamEvent`, etc.

        Raises:
            RuntimeError: If the agent is missing `ThreadManager` or `Agency` linkage.
            ValueError: If `sender_name` is provided but `chat_id` is missing.
            AgentsException: If an error occurs during the `agents.Runner` execution setup.
                             Errors during streaming are yielded as error events.
        """
        # --- Early input validation ---
        if message is None:
            logger.error("message cannot be None")
            yield {"type": "error", "content": "message cannot be None"}
            return
        if isinstance(message, str) and not message.strip():
            logger.error("message cannot be empty")
            yield {"type": "error", "content": "message cannot be empty"}
            return
        # --- End input validation ---

        # Ensure internal state is ready
        if self._thread_manager is None:
            raise RuntimeError("ThreadManager is not initialized")

        # Determine effective chat_id
        effective_chat_id: str | None = chat_id

        if effective_chat_id is None:
            # chat_id was not provided
            if sender_name is not None:
                # Agent-to-agent communication requires a chat_id
                raise ValueError("chat_id is required for agent-to-agent stream communication.")
            else:
                # User interaction without a provided chat_id
                # Generate a new chat ID, do not rely on persisted state
                effective_chat_id = f"chat_{uuid.uuid4()}"
                logger.info(f"New user stream interaction, generated chat_id: {effective_chat_id}")

        if not self._thread_manager:
            raise RuntimeError("ThreadManager is not initialized")

        # We should now have a valid effective_chat_id
        if effective_chat_id is None:
            # This should be unreachable if logic is correct
            raise RuntimeError("Internal Error: Failed to determine effective chat_id for stream.")

        logger.info(f"Agent '{self.name}' handling get_response_stream for chat_id: {effective_chat_id}")

        # Add user message to thread *before* starting the run, only if sender is None (user)
        if sender_name is None:
            try:
                thread = self._thread_manager.get_thread(effective_chat_id)
                items_to_add = ItemHelpers.input_to_new_input_list(message)  # Convert string to dict list
                # Ensure thread object supports add_items if necessary, or handle via manager
                # thread.add_items(items_to_add)
                self._thread_manager.add_items_and_save(thread, items_to_add)
                logger.debug(f"Added user message to thread {effective_chat_id} before streaming.")
            except Exception as e:
                logger.error(f"Error processing input message for stream: {e}", exc_info=True)
                yield {"type": "error", "content": f"Invalid input message format: {e}"}  # Yield error event
                return  # Stop the generator

        # Prepare context, hooks, and config
        try:
            master_context = self._prepare_master_context(context_override, effective_chat_id)
            hooks_to_use = hooks_override or self.hooks
            effective_run_config = run_config_override or RunConfig()
        except RuntimeError as e:
            # Catch errors from _prepare_master_context (e.g., missing agency)
            logger.error(f"Error preparing context/hooks for stream: {e}", exc_info=True)
            # Re-raise the critical context preparation error
            raise e
            # yield {"type": "error", "content": f"Error preparing context/hooks: {e}"}
            # return

        print("Thread items:", thread.items)

        # Execute via Runner stream
        final_result_items = []  # To capture items for potential post-processing
        try:
            logger.debug(f"Calling Runner.run_streamed for agent '{self.name}'...")
            result = Runner.run_streamed(
                starting_agent=self,
                input=thread.items if sender_name is None else [],  # Runner handles input logic from thread
                context=master_context,
                hooks=hooks_to_use,
                run_config=effective_run_config,
                max_turns=kwargs.get("max_turns", DEFAULT_MAX_TURNS),
                previous_response_id=kwargs.get("previous_response_id"),
            )
            async for event in result.stream_events():
                yield event
                # Collect RunItems from the stream events if needed
                if isinstance(event, RunItemStreamEvent):
                    final_result_items.append(event.item)

            logger.info(f"Runner.run_streamed completed for agent '{self.name}'.")

        except Exception as e:
            logger.error(f"Error during Runner.run_streamed for agent '{self.name}': {e}", exc_info=True)
            yield {"type": "error", "content": f"Runner execution failed: {e}"}  # Yield error event
            return  # Stop the generator after yielding error

        # Optional post-streaming actions (like validation, final save) can be added here
        # if necessary, using final_result_items.
        # Example: Save final assistant messages/tool calls if required by persistence model
        # Note: SDK Runner itself handles state within a run via context/hooks.

    # --- Helper Methods ---
    def _run_item_to_tresponse_input_item(self, item: RunItem) -> TResponseInputItem | None:
        """Converts a RunItem into the TResponseInputItem dictionary format for history.
        Returns None if the item type shouldn't be added to history directly.
        """

        if isinstance(item, MessageOutputItem):
            # Extract text content for simplicity; complex content needs more handling
            content = ItemHelpers.text_message_output(item)
            logger.debug(f"Converting MessageOutputItem to history: role=assistant, content='{content[:50]}...'")
            return {"role": "assistant", "content": content}

        elif isinstance(item, ToolCallItem):
            # Construct tool_calls list
            tool_calls = []
            # Handle different raw_item types within ToolCallItem
            if isinstance(item.raw_item, ResponseFunctionToolCall):
                # Access attributes directly from ResponseFunctionToolCall
                call_id = getattr(item.raw_item, "call_id", None)
                func_name = getattr(item.raw_item, "name", None)
                func_args = getattr(item.raw_item, "arguments", None)

                if not call_id or not func_name:
                    logger.warning(f"Missing call_id or name in ResponseFunctionToolCall: {item.raw_item}")
                    return None

                # Need to handle potential serialization issues with func_args
                # It's often a string already, but might be dict/list
                if isinstance(func_args, dict | list):
                    args_str = json.dumps(func_args)
                elif isinstance(func_args, str):
                    args_str = func_args
                else:
                    args_str = str(func_args)  # Fallback

                logger.debug(
                    f"Converting ToolCallItem (Function) to history: id={call_id}, name={func_name}, args='{args_str[:50]}...'"
                )
                tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": func_name, "arguments": args_str},
                    }
                )
            # Add elif blocks here for other tool call types if needed
            # elif isinstance(item.raw_item, ResponseComputerToolCall): ...
            # elif isinstance(item.raw_item, ResponseFileSearchToolCall): ...
            else:
                logger.warning(f"Unhandled raw_item type in ToolCallItem: {type(item.raw_item)}")
                return None  # Or handle appropriately

            if tool_calls:
                # Ensure content is None when tool_calls are present
                return {"role": "assistant", "content": None, "tool_calls": tool_calls}
            else:
                return None  # No valid tool calls extracted

        elif isinstance(item, ToolCallOutputItem):
            # Construct tool call output item
            tool_call_id = None
            output_content = str(item.output)  # Use the processed output
            # Check structure instead of isinstance for TypedDict
            if isinstance(item.raw_item, dict) and item.raw_item.get("type") == "function_call_output":
                tool_call_id = item.raw_item.get("call_id")
                logger.debug(
                    f"Converting ToolCallOutputItem (Function) to history: tool_call_id={tool_call_id}, content='{output_content[:50]}...'"
                )

            # Add similar checks here if handling ComputerCallOutput, etc.
            # elif isinstance(item.raw_item, dict) and item.raw_item.get('type') == 'computer_call_output':
            #     tool_call_id = item.raw_item.get("call_id")
            #     logger.debug(f"Converting ToolCallOutputItem (Computer) to history: tool_call_id={tool_call_id}, content='{output_content[:50]}...'")

            if tool_call_id:
                # Content should be stringified output
                return {"role": "tool", "tool_call_id": tool_call_id, "content": output_content}
            else:
                logger.warning(f"Could not determine tool_call_id for ToolCallOutputItem: {item.raw_item}")
                return None

        # Add handling for other RunItem types if needed (e.g., HandoffOutputItem?)
        # elif isinstance(item, UserInputItem) -> Should already be handled when initially added

        else:
            logger.debug(f"Skipping RunItem type {type(item).__name__} for thread history saving.")
            return None

    def _prepare_master_context(self, context_override: dict[str, Any] | None, chat_id: str | None) -> MasterContext:
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
            chat_id=chat_id,  # Pass chat_id to context
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

    # --- Agency Configuration Methods --- (Called by Agency)
    def _set_thread_manager(self, manager: ThreadManager):
        """Allows the Agency to inject the ThreadManager instance."""
        self._thread_manager = manager

    def _set_agency_instance(self, agency: Any):
        """Allows the Agency to inject a reference to itself and its agent map."""
        if not hasattr(agency, "agents"):
            raise TypeError("Provided agency instance must have an 'agents' dictionary.")
        self._agency_instance = agency
