import asyncio
import inspect
import json
import logging
import os
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
from agents.strict_schema import ensure_strict_json_schema
from agents.tool import FunctionTool
from openai import AsyncOpenAI, NotFoundError
from openai.types.responses import ResponseFileSearchToolCall, ResponseFunctionToolCall

from .context import MasterContext
from .thread import ThreadManager
from .tools import BaseTool
from .tools.send_message import SendMessage
from .tools.utils import from_openapi_schema, validate_openapi_spec

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
        _openai_client (AsyncOpenAI | None): Internal reference to the initialized AsyncOpenAI client instance.
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
    _openai_client: AsyncOpenAI | None = None

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

        # --- Internal State Init ---
        self._openai_client = None
        self._subagents = {}
        # _thread_manager and _agency_instance are injected by Agency

        # --- Setup ---
        self._load_tools_from_folder()  # Placeholder call
        self._parse_schemas()
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
                        with open(f_path, "r") as f:
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
    def _parse_files_folder_for_vs_id(self) -> None:
        """Synchronously parses files_folder for VS ID and sets path."""
        self.files_folder_path = None
        self._associated_vector_store_id = None  # Reset

        if not self.files_folder:
            return

        folder_str = str(self.files_folder)
        base_path_str = folder_str
        # Regex to capture base path and a VS ID that itself starts with 'vs_'
        vs_id_match = re.search(r"(.+)_vs_(vs_[a-zA-Z0-9_]+)$", folder_str)

        if vs_id_match:
            base_path_str = vs_id_match.group(1)
            self._associated_vector_store_id = vs_id_match.group(2)
            logger.info(
                f"Agent {self.name}: Parsed Vector Store ID '{self._associated_vector_store_id}' from files_folder '{folder_str}'. Base path: '{base_path_str}'"
            )
        else:
            logger.info(
                f"Agent {self.name}: files_folder '{folder_str}' does not specify a Vector Store ID with '_vs_' suffix. Local file management only."
            )

        self.files_folder_path = Path(base_path_str).resolve()
        try:
            self.files_folder_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Agent {self.name}: Ensured local files folder exists at {self.files_folder_path}")
        except OSError as e:
            logger.error(f"Agent {self.name}: Error creating files_folder at {self.files_folder_path}: {e}")
            self.files_folder_path = None
            if self._associated_vector_store_id:
                self._associated_vector_store_id = None  # Invalidate if folder creation fails
            return

        # Add FileSearchTool tentatively if VS ID is parsed. Actual VS check is async.
        if self._associated_vector_store_id:
            self._ensure_file_search_tool()  # This method is synchronous

    async def _init_file_handling(self) -> None:
        """
        Asynchronously initializes file handling by verifying/retrieving the
        associated Vector Store on OpenAI if an ID was parsed.
        This method should be called after agent instantiation in an async context.
        """
        # Ensure synchronous parts have run (idempotent checks or rely on __init__ call)
        if self.files_folder and not self.files_folder_path:
            self._parse_files_folder_for_vs_id()  # Ensure path and tentative VS ID are set

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
            # If successful, ensure FileSearchTool is correctly configured (might be redundant if _ensure_file_search_tool was robust)
            # self._ensure_file_search_tool() # Already called in sync part, but could re-verify here if needed
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

    def _ensure_file_search_tool(self):
        """
        Ensures that a FileSearchTool is available and configured if the agent
        has an associated Vector Store ID (`self._associated_vector_store_id`).

        If the tool is not present, it's added. If present but not configured with
        the agent's Vector Store ID, the ID is added to its configuration.
        """
        if not self._associated_vector_store_id:
            logger.debug(f"Agent {self.name}: No associated vector store ID; FileSearchTool setup skipped.")
            return

        file_search_tool_exists = any(isinstance(tool, FileSearchTool) for tool in self.tools)

        if not file_search_tool_exists:
            logger.info(
                f"Agent {self.name}: Adding FileSearchTool as vector store ID '{self._associated_vector_store_id}' is associated."
            )
            self.add_tool(FileSearchTool(vector_store_ids=[self._associated_vector_store_id]))
        else:
            for tool in self.tools:
                if isinstance(tool, FileSearchTool):
                    if not tool.vector_store_ids:
                        tool.vector_store_ids = [self._associated_vector_store_id]
                        logger.info(
                            f"Agent {self.name}: Configured existing FileSearchTool with vector store ID '{self._associated_vector_store_id}'."
                        )
                    elif self._associated_vector_store_id not in tool.vector_store_ids:
                        tool.vector_store_ids.append(self._associated_vector_store_id)
                        logger.info(
                            f"Agent {self.name}: Added vector store ID '{self._associated_vector_store_id}' to existing FileSearchTool."
                        )
                    break  # Assume only one FileSearchTool

    async def upload_file(self, file_path: str) -> str:
        """
        Uploads a file to OpenAI and optionally associates it with the agent's
        Vector Store if `self._associated_vector_store_id` is set (derived from
        `files_folder` using the `_vs_<id>` naming convention).

        The file is copied into the agent's local `files_folder_path` after being
        renamed to include the OpenAI File ID (e.g., `original_name_<file_id>.ext`).
        This helps prevent re-uploading the same file.

        Args:
            file_path (str): The path to the local file to upload.

        Returns:
            str: The OpenAI File ID of the uploaded file.

        Raises:
            FileNotFoundError: If the `file_path` does not exist.
            AgentsException: If the upload or Vector Store association fails.
        """
        fpath = Path(file_path)
        if not fpath.exists():
            raise FileNotFoundError(f"File not found at {file_path}")

        if not self.files_folder_path:
            # This case implies files_folder was not set or creation failed.
            # We could upload to OpenAI generally, but the convention is to manage
            # files within a files_folder context for this method.
            raise AgentsException(
                f"Agent {self.name}: Cannot upload file. Agent_files_folder_path is not set. Please initialize the agent with a valid 'files_folder'."
            )

        # Check if a version of this file (with an ID) already exists locally
        # This is a simple check; more robust would involve checking remote file IDs if available
        # For now, local name check prevents re-upload if local copy with ID exists.
        existing_file_id = await self.check_file_exists(fpath.name)
        if existing_file_id:
            logger.info(f"File {fpath.name} with ID {existing_file_id} already exists locally. Skipping upload.")
            return existing_file_id

        try:
            with open(fpath, "rb") as f:
                uploaded_file = await self.client.files.create(file=f, purpose="assistants")
            logger.info(
                f"Agent {self.name}: Successfully uploaded file {fpath.name} to OpenAI. File ID: {uploaded_file.id}"
            )
        except Exception as e:
            logger.error(f"Agent {self.name}: Failed to upload file {fpath.name} to OpenAI: {e}")
            raise AgentsException(f"Failed to upload file {fpath.name} to OpenAI: {e}") from e

        # Copy to agent's files_folder_path and rename with OpenAI ID
        try:
            new_filename = f"{fpath.stem}_{uploaded_file.id}{fpath.suffix}"
            destination_path = self.files_folder_path / new_filename
            shutil.copy(fpath, destination_path)
            logger.info(f"Agent {self.name}: Copied uploaded file to {destination_path}")
        except Exception as e:
            logger.warning(
                f"Agent {self.name}: Failed to copy file {fpath.name} to {self.files_folder_path}. File ID: {uploaded_file.id}. Error: {e}"
            )
            # Not raising an exception here as the file is uploaded to OpenAI,
            # but local copy failed. The File ID is still returned.

        # Associate with Vector Store if one is linked to this agent via files_folder
        if self._associated_vector_store_id:
            try:
                # First, check if the vector store still exists.
                try:
                    await self.client.vector_stores.retrieve(vector_store_id=self._associated_vector_store_id)
                    logger.debug(
                        f"Agent {self.name}: Confirmed Vector Store {self._associated_vector_store_id} exists before associating file {uploaded_file.id}."
                    )
                except NotFoundError:
                    logger.warning(
                        f"Agent {self.name}: Vector Store {self._associated_vector_store_id} not found during file {uploaded_file.id} association. "
                        "It might have been deleted after agent initialization. Skipping association."
                    )
                    return uploaded_file.id  # File is uploaded, but association is skipped. Early exit.

                # If VS exists, proceed to associate the file
                await self.client.vector_stores.files.create(
                    vector_store_id=self._associated_vector_store_id, file_id=uploaded_file.id
                )
                logger.info(
                    f"Agent {self.name}: Associated file {uploaded_file.id} with Vector Store {self._associated_vector_store_id}."
                )
            except Exception as e:
                logger.error(
                    f"Agent {self.name}: Failed to associate file {uploaded_file.id} with Vector Store {self._associated_vector_store_id}: {e}"
                )
                # Don't raise an exception here if association fails.

        return uploaded_file.id

    async def check_file_exists(self, file_name_or_path: str) -> str | None:
        """
        Checks if a file with a given original name (or full path) likely exists
        as an uploaded file in the agent's local `files_folder_path` by looking
        for a version of it with an appended OpenAI File ID.

        Args:
            file_name_or_path (str): The original name of the file (e.g., 'document.pdf')
                                     or the full path to the original file.

        Returns:
            str | None: The OpenAI File ID if a matching file is found, otherwise None.
        """
        if not self.files_folder_path:
            return None

        original_path = Path(file_name_or_path)
        original_stem = original_path.stem
        original_suffix = original_path.suffix

        # Search for files in files_folder_path that match the pattern: original_stem_file-ID.original_suffix
        # Example: document_file-abc123xyz.pdf
        # OpenAI File IDs usually start with 'file-'
        pattern = re.compile(f"^{re.escape(original_stem)}_(file-[a-zA-Z0-9]+){re.escape(original_suffix)}$")

        for f_path in self.files_folder_path.iterdir():
            if f_path.is_file():
                match = pattern.match(f_path.name)
                if match:
                    file_id = match.group(1)
                    logger.debug(
                        f"Found existing file {f_path.name} with ID {file_id} for original name {file_name_or_path}"
                    )
                    return file_id
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
        """Run the agent's turn, returning the full execution result."""
        if not self._thread_manager:
            raise RuntimeError(f"Agent '{self.name}' missing ThreadManager.")
        if not self._agency_instance or not hasattr(self._agency_instance, "agents"):
            raise RuntimeError(f"Agent '{self.name}' missing Agency instance or agents map.")

        effective_chat_id = chat_id
        if sender_name is None and not effective_chat_id:
            effective_chat_id = f"chat_{uuid.uuid4()}"
            logger.info(f"New user interaction, generated chat_id: {effective_chat_id}")
        elif sender_name is not None and not effective_chat_id:
            raise ValueError("chat_id is required for agent-to-agent communication within get_response.")

        logger.info(f"Agent '{self.name}' handling get_response for chat_id: {effective_chat_id}")
        thread = self._thread_manager.get_thread(effective_chat_id)

        processed_current_message_items: list[TResponseInputItem]
        try:
            processed_current_message_items = ItemHelpers.input_to_new_input_list(message)
        except Exception as e:
            logger.error(f"Error processing current input message for get_response: {e}", exc_info=True)
            raise AgentsException(f"Failed to process input message for agent {self.name}") from e

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

        logger.info(
            f"AGENT_GET_RESPONSE: History for Runner in agent '{self.name}' for chat '{effective_chat_id}' (length {len(history_for_runner)}):"
        )
        for i, history_item in enumerate(history_for_runner):
            # Limiting log length for potentially long content
            content_preview = str(history_item.get("content"))[:100]
            tool_calls_preview = str(history_item.get("tool_calls"))[:100]
            logger.info(
                f"AGENT_GET_RESPONSE: History item [{i}]: role={history_item.get('role')}, content='{content_preview}...', tool_calls='{tool_calls_preview}...'"
            )

        message_files_from_kwargs = kwargs.get("message_files")
        if message_files_from_kwargs and isinstance(message_files_from_kwargs, list) and history_for_runner:
            last_message_item = history_for_runner[-1]
            if isinstance(last_message_item, dict):
                attachments_to_add_to_last_item = []
                for file_id in message_files_from_kwargs:
                    if isinstance(file_id, str) and file_id.startswith("file-"):
                        attachments_to_add_to_last_item.append({"file_id": file_id, "tools": [{"type": "file_search"}]})
                    else:
                        logger.warning(f"Invalid file_id format in message_files: {file_id} for agent {self.name}")

                if attachments_to_add_to_last_item:
                    if "attachments" not in last_message_item:
                        last_message_item["attachments"] = []

                    existing_file_ids_in_last = {
                        att.get("file_id")
                        for att in last_message_item.get("attachments", [])
                        if isinstance(att, dict) and att.get("file_id")
                    }
                    for att_to_add in attachments_to_add_to_last_item:
                        if att_to_add["file_id"] not in existing_file_ids_in_last:
                            last_message_item["attachments"].append(att_to_add)
            else:
                logger.warning(
                    f"Cannot add attachments to agent {self.name}: Last item in history_for_runner is not a dict. "
                    f"Type: {type(last_message_item)}. Skipping attachment."
                )

        try:
            logger.debug(f"Calling Runner.run for agent '{self.name}' with {len(history_for_runner)} history items.")
            run_result: RunResult = await Runner.run(
                starting_agent=self,
                input=thread.items,  # Runner handles adding this initial input
                context=self._prepare_master_context(context_override, effective_chat_id),
                hooks=hooks_override or self.hooks,
                run_config=run_config or RunConfig(),
                max_turns=kwargs.get("max_turns", DEFAULT_MAX_TURNS),
                previous_response_id=kwargs.get("previous_response_id"),
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
                thread = self._thread_manager.get_thread(effective_chat_id)
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
        chat_id: str | None = None,
        context_override: dict[str, Any] | None = None,
        hooks_override: RunHooks | None = None,
        run_config_override: RunConfig | None = None,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:
        """Runs the agent's turn in streaming mode."""
        if message is None:
            logger.error("message cannot be None")
            yield {"type": "error", "content": "message cannot be None"}
            return
        if isinstance(message, str) and not message.strip():
            logger.error("message cannot be empty")
            yield {"type": "error", "content": "message cannot be empty"}
            return

        if self._thread_manager is None:
            # This should ideally be caught by type checkers or earlier validation
            # if _thread_manager is essential for agent functionality.
            logger.error(f"Agent '{self.name}' missing ThreadManager for streaming.")
            raise RuntimeError(f"Agent '{self.name}' missing ThreadManager.")

        effective_chat_id: str
        if chat_id is None:
            if sender_name is not None:
                logger.error(f"Agent '{self.name}': chat_id is required for agent-to-agent stream communication.")
                raise ValueError("chat_id is required for agent-to-agent stream communication.")
            else:
                effective_chat_id = f"chat_{uuid.uuid4()}"
                logger.info(
                    f"New user stream interaction for agent '{self.name}', generated chat_id: {effective_chat_id}"
                )
        else:
            effective_chat_id = chat_id

        logger.info(f"Agent '{self.name}' handling get_response_stream for chat_id: {effective_chat_id}")
        thread = self._thread_manager.get_thread(effective_chat_id)

        try:
            processed_initial_messages = ItemHelpers.input_to_new_input_list(message)
            self._thread_manager.add_items_and_save(thread, processed_initial_messages)
            logger.debug(
                f"Added initial message to thread {effective_chat_id} before streaming for agent '{self.name}'."
            )
        except Exception as e:
            logger.error(f"Error processing input message for stream agent '{self.name}': {e}", exc_info=True)
            yield {"type": "error", "content": f"Invalid input message format: {e}"}
            return

        try:
            master_context = self._prepare_master_context(context_override, effective_chat_id)
            hooks_to_use = hooks_override or self.hooks
            effective_run_config = run_config_override or RunConfig()
        except RuntimeError as e:
            logger.error(f"Error preparing context/hooks for stream agent '{self.name}': {e}", exc_info=True)
            raise e  # Re-raise critical context preparation error

        final_result_items = []
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
                        # Avoid adding items that might effectively be duplicates of the initial input if not handled carefully
                        # This check might be too simplistic and depend on exact item structure / IDs if available
                        is_duplicate = False
                        if processed_initial_messages:
                            # This simple check may not be robust enough for all cases.
                            # It assumes that if a generated item is identical to an initial one, it might be a duplicate.
                            # A more robust check would compare based on unique IDs if available, or more specific content fields.
                            if item_dict in processed_initial_messages and item_dict.get("role") == "user":
                                is_duplicate = (
                                    True  # Avoid re-adding the initial user message if it somehow appears in output
                                )

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
                    tool_call_id_for_array = getattr(raw, "call_id", getattr(raw, "id", None))
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
                        func_args_str = json.dumps({"queries": getattr(raw, "queries", [])})
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

            # Attempt to retrieve the tool_call_id, prioritizing direct attribute if SDK provides it
            if hasattr(item, "tool_call_id") and item.tool_call_id:
                tool_call_id = item.tool_call_id
            # Fallback: check raw_item if it's the ResponseFunctionToolCall or a dict containing call_id
            elif isinstance(item.raw_item, ResponseFunctionToolCall):
                # ResponseFunctionToolCall from /v1/responses has 'call_id' for matching, and 'id' for its own unique ID
                tool_call_id = getattr(item.raw_item, "call_id", None)
                if tool_call_id is None:  # Should not happen if call_id is reliable
                    tool_call_id = getattr(item.raw_item, "id", None)  # Less reliable for matching
            elif isinstance(item.raw_item, dict) and "call_id" in item.raw_item:
                tool_call_id = item.raw_item.get("call_id")

            if tool_call_id:
                logger.debug(
                    f"Converting ToolCallOutputItem to history: tool_call_id={tool_call_id}, content='{output_content[:50]}...'"
                )
                return {"role": "tool", "tool_call_id": tool_call_id, "content": output_content}
            else:
                logger.warning(
                    f"Could not determine tool_call_id for ToolCallOutputItem: raw_item={item.raw_item}, item={item}"
                )
                return None
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
        except (TypeError, OSError, AttributeError) as e:
            # If that fails, fall back to inspect
            try:
                class_file = inspect.getfile(self.__class__)
            except (TypeError, OSError, AttributeError) as e:
                return "./"
            return os.path.abspath(os.path.realpath(os.path.dirname(class_file)))
