import logging
import os
import re
from pathlib import Path

from agents import CodeInterpreterTool, FileSearchTool
from agents.exceptions import AgentsException
from openai import NotFoundError
from openai.types.responses.tool_param import CodeInterpreter

logger = logging.getLogger(__name__)


class AgentFileManager:
    code_interpreter_file_extensions = [
        ".c",
        ".cs",
        ".cpp",
        ".html",
        ".java",
        ".php",
        ".py",
        ".rb",
        ".tex",
        ".css",
        ".js",
        ".sh",
        ".ts",
        ".csv",
        ".pkl",
        ".tar",
        ".xlsx",
        ".xml",
        ".zip",
    ]

    def __init__(self, agent):
        self.agent = agent

    def upload_file(self, file_path: str, include_in_vector_store: bool = True) -> str:
        """
        Uploads a file to OpenAI and optionally associates it with the agent's
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

        folder_path = Path(self.agent.files_folder)
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

        folder_str = str(self.agent.files_folder)
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
            if Path(file).suffix.lower() in self.code_interpreter_file_extensions:
                file_id = self.upload_file(
                    os.path.join(self.agent.files_folder_path, file), include_in_vector_store=False
                )
                code_interpreter_file_ids.append(file_id)
            else:
                self.upload_file(os.path.join(self.agent.files_folder_path, file))

        # Process new files found in original directory
        for new_file in new_files_to_process:
            logger.info(f"Agent {self.agent.name}: Processing new file {new_file.name}")

            # Upload the new file (this will automatically rename it with file ID and move to vector store dir)
            if new_file.suffix.lower() in self.code_interpreter_file_extensions:
                file_id = self.upload_file(str(new_file), include_in_vector_store=False)
                code_interpreter_file_ids.append(file_id)
            else:
                self.upload_file(str(new_file))

        # Add FileSearchTool tentatively if VS ID is parsed. Actual VS check is async.
        if self.agent._associated_vector_store_id:
            self.add_file_search_tool()  # This method is synchronous
        else:
            logger.error(f"Agent {self.agent.name}: No associated vector store ID; FileSearchTool setup skipped.")

        if code_interpreter_file_ids:
            self.add_code_interpreter_tool(code_interpreter_file_ids)

    def add_file_search_tool(self, file_ids: list[str] = None):
        """
        Ensures that a FileSearchTool is available and configured if the agent
        has an associated Vector Store ID (`self.agent._associated_vector_store_id`).
        If optional file_ids provided, they will be added to the associated vector store.

        If the tool is not present, it will be added. If present but not configured with
        the agent's Vector Store ID, the ID is added to its configuration.
        """
        file_search_tool_exists = any(isinstance(tool, FileSearchTool) for tool in self.agent.tools)

        if not self.agent._associated_vector_store_id and not file_search_tool_exists and not file_ids:
            logger.debug(f"Agent {self.agent.name}: No associated vector store ID; FileSearchTool setup skipped.")
            return
        elif not self.agent._associated_vector_store_id and not file_search_tool_exists and file_ids:
            self.agent._associated_vector_store_id = self.init_attachments_vs(
                vs_name=f"attachments_vs_{self.agent.name}"
            )

        if not file_search_tool_exists:
            logger.info(
                f"Agent {self.agent.name}: Adding FileSearchTool with vector store ID: "
                f"'{self.agent._associated_vector_store_id}'"
            )
            if file_ids:
                self.add_files_to_vector_store(file_ids)
            self.agent.add_tool(FileSearchTool(vector_store_ids=[self.agent._associated_vector_store_id]))
            logger.info(
                f"Agent {self.agent.name}: FileSearchTool added with vector store ID: "
                f"'{self.agent._associated_vector_store_id}'"
            )
        else:
            for tool in self.agent.tools:
                if isinstance(tool, FileSearchTool):
                    if not tool.vector_store_ids:
                        raise AgentsException(
                            f"Agent {self.agent.name}: FileSearchTool has no vector store IDs. "
                            "Please provide vector store IDs when adding the tool."
                        )

                    # If tool was provided without files folder, associate agent's vs with one of the tool's vs ids.
                    if not self.agent._associated_vector_store_id:
                        self.agent._associated_vector_store_id = tool.vector_store_ids[0]

                    # Add files folder vs id to the tool if it's not already there.
                    if self.agent._associated_vector_store_id not in tool.vector_store_ids:
                        tool.vector_store_ids.append(self.agent._associated_vector_store_id)
                        logger.info(
                            f"Agent {self.agent.name}: Added vector store ID "
                            f"'{self.agent._associated_vector_store_id}' to existing FileSearchTool."
                        )
                    if file_ids and self.agent._associated_vector_store_id:
                        self.add_files_to_vector_store(file_ids)

                    break  # Assume only one FileSearchTool

    def add_code_interpreter_tool(self, code_interpreter_file_ids: list[str]):
        """
        Checks that a CodeInterpreterTool is available and configured.

        If the tool is not present, it will be added. If present but not configured with
        the file IDs, the file IDs are added to its configuration.
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
                    if isinstance(tool.tool_config.get("container", ""), str):
                        logger.warning(
                            f"Agent {self.agent.name}: Cannot add files to container for code interpreter, "
                            "add them manually or switch to using id list."
                        )
                    elif code_interpreter_file_ids:
                        existing_file_ids = tool.tool_config.container.get("file_ids", [])
                        for file_id in code_interpreter_file_ids:
                            if file_id in existing_file_ids:
                                logger.info(
                                    f"Agent {self.agent.name}: File {file_id} already in "
                                    f"CodeInterpreterTool, skipping..."
                                )
                                continue
                            existing_file_ids.append(file_id)
                        tool.tool_config.container["file_ids"] = existing_file_ids
                        logger.info(
                            f"Agent {self.agent.name}: Added file IDs "
                            f"{code_interpreter_file_ids} to existing CodeInterpreter."
                        )
                    break  # Assume only one CodeInterpreterTool

    def add_files_to_vector_store(self, file_ids: list[str]):
        """
        Adds a file to the agent's Vector Store if one is linked to this agent via files_folder
        """
        if self.agent._associated_vector_store_id:
            existing_files = self.agent.client_sync.vector_stores.files.list(
                vector_store_id=self.agent._associated_vector_store_id
            )
            existing_file_ids = [file.id for file in existing_files.data]
            for file_id in file_ids:
                if file_id in existing_file_ids:
                    logger.info(
                        f"Agent {self.agent.name}: File {file_id} already in "
                        f"Vector Store {self.agent._associated_vector_store_id}, skipping..."
                    )
                    continue

                try:
                    self.agent.client_sync.vector_stores.files.create(
                        vector_store_id=self.agent._associated_vector_store_id, file_id=file_id
                    )
                    logger.info(
                        f"Agent {self.agent.name}: Added file {file_id} "
                        f"to Vector Store {self.agent._associated_vector_store_id}."
                    )
                except Exception as e:
                    logger.error(
                        f"Agent {self.agent.name}: Failed to add file {file_id} "
                        f"to Vector Store {self.agent._associated_vector_store_id}: {e}"
                    )
                    raise AgentsException(
                        f"Failed to add file {file_id} to Vector Store {self.agent._associated_vector_store_id}: {e}"
                    ) from e

    def get_filename_by_id(self, file_id: str) -> str:
        """
        Get the filename of a file by its ID
        """
        file_data = self.agent.client_sync.files.retrieve(file_id)
        return file_data.filename

    def init_attachments_vs(self, vs_name: str = "attachments_vs"):
        """
        Fallback function that would create (or retrieve) a new vector store in case
        no vector stores were provided by the user.
        """
        # First find if attachments_vs already exists
        logger.info(f"Using a fallback vector store for agent {self.agent.name}: {vs_name}")
        existing_vs = self.agent.client_sync.vector_stores.list()
        existing_vs_names = [vs.name for vs in existing_vs.data]
        if vs_name in existing_vs_names:
            return existing_vs.data[existing_vs_names.index(vs_name)].id
        else:
            created_vs = self.agent.client_sync.vector_stores.create(name=vs_name)
            return created_vs.id

    def sort_file_attachments(self, file_ids: list[str]) -> list[dict]:
        """
        Helper function to correctly distribute file ids into file search, code interpreter and pdf file ids.
        If any files can be included in the message, they will be returned in the content_list.
        """
        file_search_ids = []
        pdf_file_ids = []
        code_interpreter_ids = []
        for file_id in file_ids:
            filename = self.get_filename_by_id(file_id)
            extension = Path(filename).suffix.lower()
            if extension in self.code_interpreter_file_extensions:
                code_interpreter_ids.append(file_id)
            elif extension == ".pdf":
                pdf_file_ids.append(file_id)
            else:
                file_search_ids.append(file_id)

        # Add file items to content
        content_list = []
        for file_id in pdf_file_ids:
            if isinstance(file_id, str) and file_id.startswith("file-"):
                logger.debug(f"Adding pdf file content item for file_id: {file_id}")
                file_content_item = {
                    "type": "input_file",
                    "file_id": file_id,
                }
                content_list.append(file_content_item)
                logger.debug(f"Added file content item for file_id: {file_id}")
            else:
                logger.warning(f"Invalid file_id format: {file_id} for agent {self.agent.name}")

        # ------------------------------------------------------------
        # Temporary solution until openai supports other file types.
        # ------------------------------------------------------------
        # Add file search and code interpreter tools if needed (will not overwrite existing tools)
        if file_search_ids:
            logger.info(f"Adding file search tool for agent {self.agent.name} with file ids: {file_search_ids}")
            self.add_file_search_tool(file_search_ids)
        if code_interpreter_ids:
            logger.info(
                f"Adding code interpreter tool for agent {self.agent.name} with file ids: {code_interpreter_ids}"
            )
            self.add_code_interpreter_tool(code_interpreter_ids)

        return content_list
