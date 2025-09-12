import logging
import os
import re
from pathlib import Path
from typing import Any

from agents import CodeInterpreterTool, FileSearchTool
from agents.exceptions import AgentsException
from openai import NotFoundError
from openai.types.responses.tool_param import CodeInterpreter

logger = logging.getLogger(__name__)

# Shared constants
CODE_INTERPRETER_FILE_EXTENSIONS = [
    ".c",
    ".cs",
    ".cpp",
    ".csv",
    ".html",
    ".java",
    ".json",
    ".php",
    ".py",
    ".rb",
    ".css",
    ".js",
    ".sh",
    ".ts",
    ".pkl",
    ".tar",
    ".xlsx",
    ".xml",
    ".zip",
]

FILE_SEARCH_FILE_EXTENSIONS = [".doc", ".docx", ".go", ".md", ".pdf", ".pptx", ".tex", ".txt"]

IMAGE_FILE_EXTENSIONS = [".jpeg", ".jpg", ".gif", ".png"]


class AgentFileManager:
    """Manages permanent file operations for agents, including uploads and vector store management."""

    def __init__(self, agent):
        self.agent = agent

    def upload_file(self, file_path: str, include_in_vector_store: bool = True) -> str:
        """
        Uploads a local file to OpenAI and optionally associates it with the agent's
        Vector Store if `self.agent._associated_vector_store_id` is set (derived from
        `files_folder` using the `_vs_<id>` naming convention).

        The file is renamed to include the OpenAI File ID (e.g., `original_name_<file_id>.ext`)
        after successful upload to prevent re-uploading the same file.

        Args:
            file_path (str): The path to the local file to upload.
            include_in_vector_store (bool): Whether to associate the file with the agent's Vector Store.
        Returns:
            str: The OpenAI File ID of the uploaded file.

        Raises:
            FileNotFoundError: If the `file_path` does not exist.
            AgentsException: If the upload or Vector Store association fails.
        """
        fpath = Path(file_path)
        if not fpath.exists():
            raise FileNotFoundError(f"File not found at {file_path}")

        if not self.agent.files_folder_path:
            # This case implies files_folder was not set or creation failed.
            # We could upload to OpenAI generally, but the convention is to manage
            # files within a files_folder context for this method.
            raise AgentsException(
                f"Agent {self.agent.name}: Cannot upload file. Agent_files_folder_path is not set. "
                "Please initialize the agent with a valid 'files_folder'."
            )

        # Check if file has already been uploaded
        existing_file_id = self.get_id_from_file(fpath)
        logger.info(f"Existing file ID: {existing_file_id}")
        if existing_file_id:
            logger.info(f"File {fpath.name} with ID {existing_file_id} is already uploaded, skipping...")
            return existing_file_id

        try:
            with open(fpath, "rb") as f:
                uploaded_file = self.agent.client_sync.files.create(file=f, purpose="assistants")
            logger.info(
                f"Agent {self.agent.name}: Successfully uploaded file {fpath.name} to OpenAI. "
                f"File ID: {uploaded_file.id}"
            )
        except Exception as e:
            logger.error(f"Agent {self.agent.name}: Failed to upload file {fpath.name} to OpenAI: {e}")
            raise AgentsException(f"Failed to upload file {fpath.name} to OpenAI: {e}") from e

        # Rename the original file to include the OpenAI ID
        try:
            new_filename = f"{fpath.stem}_{uploaded_file.id}{fpath.suffix}"
            destination_path = self.agent.files_folder_path / new_filename
            fpath.rename(destination_path)
            logger.info(f"Agent {self.agent.name}: Renamed uploaded file to {destination_path}")
        except Exception as e:
            logger.warning(f"Agent {self.agent.name}: Failed to rename file {fpath.name} to {destination_path}: {e}")
            # Not raising an exception here as the file is uploaded to OpenAI,
            # but local rename failed. The File ID is still returned.

        # Associate with Vector Store if one is linked to this agent via files_folder
        if self.agent._associated_vector_store_id and include_in_vector_store:
            try:
                # First, check if the vector store still exists.
                try:
                    self.agent.client_sync.vector_stores.retrieve(
                        vector_store_id=self.agent._associated_vector_store_id
                    )
                    logger.debug(
                        f"Agent {self.agent.name}: Confirmed Vector Store {self.agent._associated_vector_store_id} "
                        f"exists before associating file {uploaded_file.id}."
                    )
                except NotFoundError:
                    logger.warning(
                        f"Agent {self.agent.name}: Vector Store {self.agent._associated_vector_store_id} "
                        f"not found during file {uploaded_file.id} association. "
                        "It might have been deleted after agent initialization. Skipping association."
                    )
                    return uploaded_file.id  # File is uploaded, but association is skipped. Early exit.

                # If VS exists, proceed to associate the file
                self.agent.client_sync.vector_stores.files.create(
                    vector_store_id=self.agent._associated_vector_store_id, file_id=uploaded_file.id
                )
                logger.info(
                    f"Agent {self.agent.name}: Associated file {uploaded_file.id} "
                    f"with Vector Store {self.agent._associated_vector_store_id}."
                )
            except Exception as e:
                logger.error(
                    f"Agent {self.agent.name}: Failed to associate file {uploaded_file.id} "
                    f"with Vector Store {self.agent._associated_vector_store_id}: {e}"
                )
                # Don't raise an exception here if association fails.

        return uploaded_file.id

    def get_id_from_file(self, f_path):
        """Get file id from file name"""
        if os.path.isfile(f_path):
            file_name, file_ext = os.path.splitext(f_path)
            file_name = os.path.basename(file_name)
            file_name = file_name.split("_")
            if len(file_name) > 1:
                return file_name[-1] if "file-" in file_name[-1] else None
            else:
                return None
        else:
            raise FileNotFoundError(f"File not found: {f_path}")

    def _parse_files_folder_for_vs_id(self) -> None:
        """Synchronously parses files_folder for VS ID and sets path."""
        self.agent.files_folder_path = None
        self.agent._associated_vector_store_id = None  # Reset

        if not self.agent.files_folder:
            return

        folder_path = Path(self.agent.get_class_folder_path()) / Path(self.agent.files_folder)
        original_folder_path = folder_path  # Keep reference to original directory

        # ALWAYS check for existing vector store directories first, regardless of original directory existence
        parent = folder_path.parent
        base_name = folder_path.name
        candidates = list(parent.glob(f"{base_name}_vs_*"))

        if candidates:
            # Use the first existing vector store directory found
            folder_path = candidates[0]
            self.agent.files_folder = str(folder_path)
            logger.info(
                f"Agent {self.agent.name}: Found existing vector store folder '{folder_path}' "
                f"- reusing instead of creating new one."
            )
        elif not folder_path.exists():
            # Try resolving relative to the class folder if not absolute
            if not folder_path.is_absolute():
                folder_path = Path(self.agent.get_class_folder_path()).joinpath(self.agent.files_folder)
            folder_path = folder_path.resolve()
            if not folder_path.is_dir():
                logger.error(f"Files folder '{folder_path}' is not a directory. Skipping...")
                return

        folder_str = str(folder_path)
        base_path_str = folder_str
        # Regex to capture base path and a VS ID that itself starts with 'vs_'
        vs_id_match = re.search(r"(.+)_(vs_[a-zA-Z0-9_]+)$", folder_str)

        if not vs_id_match:
            folder_name = Path(base_path_str).name
            openai_vs_name = folder_name
            logger.info(
                f"Agent {self.agent.name}: files_folder '{folder_str}' does not specify a Vector Store ID "
                "with '_vs_' suffix. Creating a new Vector Store."
            )
            created_vs = self.agent.client_sync.vector_stores.create(name=openai_vs_name)
            vs_id = created_vs.id
            new_folder_name = f"{folder_name}_{vs_id}"
            parent_dir = Path(base_path_str).parent
            new_folder_path = parent_dir / new_folder_name
            # Rename the folder if it exists and is not already named with the VS id
            try:
                if Path(base_path_str).exists() and Path(base_path_str).name != new_folder_name:
                    # Rename the directory to include the vector store ID
                    Path(base_path_str).rename(new_folder_path)
                    base_path_str = str(new_folder_path)
                    logger.info(f"Agent {self.agent.name}: Renamed folder to {new_folder_path}")
                elif not Path(base_path_str).exists():
                    # If the folder does not exist, create it with the new name
                    new_folder_path.mkdir(parents=True, exist_ok=True)
                    base_path_str = str(new_folder_path)
                    logger.info(f"Agent {self.agent.name}: Created files folder {new_folder_path}")
                else:
                    # Folder already has the correct name
                    base_path_str = str(Path(base_path_str).resolve())
                self.agent._associated_vector_store_id = vs_id
            except Exception as e:
                logger.error(f"Agent {self.agent.name}: Error renaming/creating files_folder to {new_folder_path}: {e}")
                self.agent.files_folder_path = None
                return
        else:
            self.agent._associated_vector_store_id = vs_id_match.group(2)

        self.agent.files_folder_path = Path(base_path_str).resolve()

        # Check for new files in the original directory when reusing vector store
        is_reusing_vector_store = candidates and original_folder_path.exists()
        new_files_to_process = []

        if is_reusing_vector_store:
            logger.info(
                f"Agent {self.agent.name}: Checking for new files in original directory '{original_folder_path}'"
            )

            # Get list of files already processed (have _file-<id> suffix) in vector store directory
            processed_files = set()
            for vs_file in self.agent.files_folder_path.iterdir():
                if vs_file.is_file() and "_file-" in vs_file.name:
                    # Extract original filename: "name_file-<id>.ext" -> "name.ext"
                    original_name = vs_file.name.split("_file-")[0] + vs_file.suffix
                    processed_files.add(original_name)

            # Check original directory for new files (not yet processed)
            for original_file in original_folder_path.iterdir():
                if original_file.is_file() and original_file.name not in processed_files:
                    logger.info(f"Agent {self.agent.name}: Found new file to process: {original_file.name}")
                    new_files_to_process.append(original_file)

        code_interpreter_file_ids = []

        # Process existing files in vector store directory
        for file in os.listdir(self.agent.files_folder_path):
            # Ideally images should be provided as attachments, but code interpreter tool can also handle images.
            if Path(file).suffix.lower() in CODE_INTERPRETER_FILE_EXTENSIONS + IMAGE_FILE_EXTENSIONS:
                file_id = self.upload_file(
                    os.path.join(self.agent.files_folder_path, file), include_in_vector_store=False
                )
                code_interpreter_file_ids.append(file_id)
            elif Path(file).suffix.lower() in FILE_SEARCH_FILE_EXTENSIONS:
                self.upload_file(os.path.join(self.agent.files_folder_path, file))
            else:
                raise AgentsException(f"Unsupported file extension: {Path(file).suffix.lower()} for file {file}")

        # Process new files found in original directory
        for new_file in new_files_to_process:
            logger.info(f"Agent {self.agent.name}: Processing new file {new_file.name}")

            # Upload the new file (this will automatically rename it with file ID and move to vector store dir)
            if new_file.suffix.lower() in CODE_INTERPRETER_FILE_EXTENSIONS + IMAGE_FILE_EXTENSIONS:
                file_id = self.upload_file(str(new_file), include_in_vector_store=False)
                code_interpreter_file_ids.append(file_id)
            elif Path(new_file).suffix.lower() in FILE_SEARCH_FILE_EXTENSIONS:
                self.upload_file(str(new_file))
            else:
                ext = Path(new_file).suffix.lower()
                raise AgentsException(f"Unsupported file extension: {ext} for file {new_file}")

        # Add FileSearchTool if VS ID is parsed.
        if self.agent._associated_vector_store_id:
            self.add_file_search_tool(vector_store_id=self.agent._associated_vector_store_id)
        else:
            logger.error(f"Agent {self.agent.name}: No associated vector store ID; FileSearchTool setup skipped.")

        if code_interpreter_file_ids:
            self.add_code_interpreter_tool(code_interpreter_file_ids)

    def add_file_search_tool(self, vector_store_id: str, file_ids: list[str] | None = None):
        """
        Adds a new vector store to the existing FileSearchTool or creates a new one if it doesn't exist.
        If optional file_ids provided, they will be added to the provided vector store.
        """
        file_search_tool_exists = any(isinstance(tool, FileSearchTool) for tool in self.agent.tools)

        if not file_search_tool_exists:
            logger.info(f"Agent {self.agent.name}: Adding FileSearchTool with vector store ID: '{vector_store_id}'")
            if file_ids:
                self.add_files_to_vector_store(vector_store_id, file_ids)

            # Create FileSearchTool with include_search_results from agent configuration
            file_search_tool = FileSearchTool(
                vector_store_ids=[vector_store_id],
                include_search_results=getattr(self.agent, "include_search_results", False),
            )
            self.agent.add_tool(file_search_tool)
            self.agent._associated_vector_store_id = vector_store_id

            logger.info(
                f"Agent {self.agent.name}: FileSearchTool added with vector store ID: "
                f"'{vector_store_id}' and include_search_results="
                f"{getattr(self.agent, 'include_search_results', False)}"
            )
        else:
            for tool in self.agent.tools:
                if isinstance(tool, FileSearchTool):
                    if not tool.vector_store_ids:
                        raise AgentsException(
                            f"Agent {self.agent.name}: FileSearchTool has no vector store IDs. "
                            "Please provide vector store IDs when adding the tool."
                        )

                    # If tool is user-defined, associate agent's vs with one of the tool's vs ids.
                    if not self.agent._associated_vector_store_id:
                        self.agent._associated_vector_store_id = tool.vector_store_ids[0]

                    # Add files folder vs id to the tool if it's not already there.
                    if vector_store_id not in tool.vector_store_ids:
                        tool.vector_store_ids.append(vector_store_id)
                        logger.info(
                            f"Agent {self.agent.name}: Added vector store ID "
                            f"'{vector_store_id}' to existing FileSearchTool."
                        )
                    if file_ids and vector_store_id:
                        self.add_files_to_vector_store(vector_store_id, file_ids)

                    break  # Assume only one FileSearchTool

    def add_code_interpreter_tool(self, code_interpreter_file_ids: list[str]):
        """
        Checks that a CodeInterpreterTool is available and configured.

        If the tool is not present, it will be added.
        If present but not configured with the file IDs, the file IDs are added to its configuration.
        If present and configured, the file IDs are added to its configuration.
        """

        code_interpreter_tool_exists = any(isinstance(tool, CodeInterpreterTool) for tool in self.agent.tools)

        if not code_interpreter_tool_exists:
            logger.info(f"Agent {self.agent.name}: Adding CodeInterpreterTool")
            self.agent.add_tool(
                CodeInterpreterTool(
                    tool_config=CodeInterpreter(
                        container={"type": "auto", "file_ids": code_interpreter_file_ids}, type="code_interpreter"
                    )
                )
            )
        else:
            for tool in self.agent.tools:
                if isinstance(tool, CodeInterpreterTool):
                    # This means that tool uses specific container, not a file id list.
                    if isinstance(tool.tool_config.get("container", ""), str):
                        logger.warning(
                            f"Agent {self.agent.name}: Cannot add files to container for code interpreter, "
                            "add them manually or switch to using file_ids list."
                        )
                    elif code_interpreter_file_ids:
                        container: Any = tool.tool_config.get("container", {})
                        if not isinstance(container, dict):
                            container = {}
                        code_interpreter_container = container
                        existing_file_ids = code_interpreter_container.get("file_ids", [])
                        for file_id in code_interpreter_file_ids:
                            if file_id in existing_file_ids:
                                logger.info(
                                    f"Agent {self.agent.name}: File {file_id} already in "
                                    f"CodeInterpreterTool, skipping..."
                                )
                                continue
                            existing_file_ids.append(file_id)
                        code_interpreter_container["file_ids"] = existing_file_ids
                        tool.tool_config["container"] = code_interpreter_container  # type: ignore[typeddict-item]
                        logger.info(
                            f"Agent {self.agent.name}: Added file IDs "
                            f"{code_interpreter_file_ids} to existing CodeInterpreter."
                        )
                    break  # Assume only one CodeInterpreterTool

    def add_files_to_vector_store(self, vector_store_id: str, file_ids: list[str]):
        """
        Adds a file to the agent's Vector Store if one is linked to this agent via files_folder
        """
        existing_files = self.agent.client_sync.vector_stores.files.list(vector_store_id=vector_store_id)
        existing_file_ids = [file.id for file in existing_files.data]
        for file_id in file_ids:
            if file_id in existing_file_ids:
                logger.info(
                    f"Agent {self.agent.name}: File {file_id} already in Vector Store {vector_store_id}, skipping..."
                )
                continue

            try:
                self.agent.client_sync.vector_stores.files.create(vector_store_id=vector_store_id, file_id=file_id)
                logger.info(f"Agent {self.agent.name}: Added file {file_id} to Vector Store {vector_store_id}.")
            except Exception as e:
                logger.error(
                    f"Agent {self.agent.name}: Failed to add file {file_id} to Vector Store {vector_store_id}: {e}"
                )
                raise AgentsException(f"Failed to add file {file_id} to Vector Store {vector_store_id}: {e}") from e

    def read_instructions(self):
        if not self.agent.instructions:
            return

        # Try class-relative path first
        class_instructions_path = os.path.normpath(os.path.join(self.get_class_folder_path(), self.agent.instructions))
        if os.path.isfile(class_instructions_path):
            with open(class_instructions_path) as f:
                self.agent.instructions = f.read()
        elif os.path.isfile(self.agent.instructions):
            # Try as absolute or CWD-relative path
            with open(self.agent.instructions) as f:
                self.agent.instructions = f.read()
        else:
            # Keep original instructions if it's not a file path
            return

    def get_class_folder_path(self):
        """Get the directory where the agent was instantiated for relative path resolution."""
        # Delegate to the agent's path resolution method for consistency
        return self.agent.get_class_folder_path()
