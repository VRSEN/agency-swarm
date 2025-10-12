import logging
import os
import re
from pathlib import Path
from typing import Any

from agents import CodeInterpreterTool, FileSearchTool
from agents.exceptions import AgentsException
from openai import NotFoundError
from openai.types.responses.tool_param import CodeInterpreter

from agency_swarm.agent.file_sync import FileSync

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
        self._sync = FileSync(agent)

    def upload_file(self, file_path: str, include_in_vector_store: bool = True) -> str:
        """Upload a local file and optionally associate it with the agent's vector store; returns file_id."""
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

        # Check if file has already been uploaded and compare mtime vs remote created_at
        existing_file_id = self.get_id_from_file(fpath)
        logger.info(f"Existing file ID: {existing_file_id}")

        if existing_file_id:
            try:
                remote_file = self.agent.client_sync.files.retrieve(existing_file_id)
                remote_created_at = getattr(remote_file, "created_at", None)
            except Exception:
                remote_created_at = None

            local_mtime = fpath.stat().st_mtime
            if isinstance(remote_created_at, int | float) and local_mtime <= float(remote_created_at):
                logger.info(f"File {fpath.name} unchanged since upload, skipping...")
                return existing_file_id
            else:
                logger.info(
                    f"File {fpath.name} appears newer locally (mtime={local_mtime}, created_at={remote_created_at});"
                    f" replacing file {existing_file_id} on OpenAI."
                )
                try:
                    # Detach from VS and delete remote file before re-upload
                    self._sync.remove_file_from_vs_and_oai(existing_file_id)
                except Exception as e:
                    logger.warning(f"Agent {self.agent.name}: Failed to remove existing file {existing_file_id}: {e}")

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

        destination_path: Path | None = None
        try:
            # Compute new filename based on the original stem without trailing _file-id if present
            base_stem = fpath.stem
            if existing_file_id and base_stem.endswith(f"_{existing_file_id}"):
                base_stem = base_stem[: -len(existing_file_id) - 1]
            new_filename = f"{base_stem}_{uploaded_file.id}{fpath.suffix}"
            destination_path = self.agent.files_folder_path / new_filename
            fpath.rename(destination_path)
            logger.info(f"Agent {self.agent.name}: Renamed uploaded file to {destination_path}")
            created_at = getattr(uploaded_file, "created_at", None)
            if destination_path and isinstance(created_at, int | float | str):
                try:
                    timestamp = float(created_at)
                    os.utime(destination_path, (timestamp, timestamp))
                except (ValueError, TypeError):
                    pass
                except OSError as err:
                    logger.debug(
                        f"Agent {self.agent.name}: Failed to align mtime for {destination_path} "
                        f"with OpenAI timestamp: {err}"
                    )
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
            file_name, _ = os.path.splitext(f_path)
            file_name = os.path.basename(file_name)
            match = re.search(r"_file-([A-Za-z0-9]{15,})$", file_name)
            if match:
                id_suffix = match.group(1)
                return f"file-{id_suffix}"
            return None
        else:
            raise FileNotFoundError(f"File not found: {f_path}")

    def parse_files_folder_for_vs_id(self) -> None:
        """Discover or create the vector store for files_folder, upload files, and wire tools."""
        self.agent.files_folder_path = None
        self.agent._associated_vector_store_id = None

        if not self.agent.files_folder:
            return

        base_folder_path = Path(self.agent.get_class_folder_path()) / Path(self.agent.files_folder)
        folder_path, candidates = self._select_vector_store_path(base_folder_path)
        original_folder_path = base_folder_path

        if folder_path is None:
            return

        if candidates:
            self.agent.files_folder = str(folder_path)
            logger.info(
                f"Agent {self.agent.name}: Found existing vector store folder '{folder_path}' "
                f"- reusing instead of creating new one."
            )

        vs_id = self._create_or_identify_vector_store(folder_path)
        if vs_id is None:
            self.agent.files_folder_path = None
            return

        self.agent._associated_vector_store_id = vs_id
        if not self.agent.files_folder_path:
            self.agent.files_folder_path = folder_path.resolve()
        folder_path = self.agent.files_folder_path

        new_files: list[Path] = []
        if candidates and original_folder_path and Path(original_folder_path).exists():
            new_files = self._find_new_files_to_process(Path(original_folder_path))

        code_interpreter_file_ids = []
        for file in os.listdir(self.agent.files_folder_path):
            if self._should_skip_file(file):
                logger.debug(f"Skipping file '{file}'")
                continue
            file_id = self._upload_file_by_type(self.agent.files_folder_path / file)
            if file_id:
                code_interpreter_file_ids.append(file_id)

        for new_file in new_files:
            file_id = self._upload_file_by_type(new_file)
            if file_id:
                code_interpreter_file_ids.append(file_id)

        if self.agent._associated_vector_store_id:
            self.add_file_search_tool(vector_store_id=self.agent._associated_vector_store_id)
        else:
            logger.error(f"Agent {self.agent.name}: No associated vector store ID; FileSearchTool setup skipped.")

        if code_interpreter_file_ids:
            self.add_code_interpreter_tool(code_interpreter_file_ids)

        # After uploads and tool wiring, ensure the vector store is in sync with local folder
        try:
            self._sync.sync_with_folder()
        except Exception as e:
            logger.error(f"Agent {self.agent.name}: Failed to sync vector store with folder: {e}")

    def add_file_search_tool(self, vector_store_id: str, file_ids: list[str] | None = None):
        """Ensure FileSearchTool references the given vector_store_id and optionally add file_ids."""
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
        """Ensure a CodeInterpreterTool exists and contains the provided file IDs."""

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
        """Add files to the vector store if not already present."""
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

    def _should_skip_file(self, filename: str) -> bool:
        return filename.startswith(".") or filename.startswith("__")

    def _select_vector_store_path(self, folder_path: Path) -> tuple[Path | None, list[Path]]:
        """Determine which directory should be used for the agent's files folder."""
        base_name = folder_path.name
        if not base_name:
            return None, []

        vs_match = re.match(r"^(.+)_vs_[a-zA-Z0-9]{15,}$", base_name)
        base_name_without_vs = vs_match.group(1) if vs_match else base_name

        candidates = [
            candidate for candidate in folder_path.parent.glob(f"{base_name_without_vs}_vs_*") if candidate.is_dir()
        ]

        if folder_path.exists() and folder_path.is_dir() and "_vs_" in base_name:
            folder_resolved = folder_path.resolve()
            resolved_candidates = [candidate.resolve() for candidate in candidates]
            if folder_resolved in resolved_candidates:
                candidates.pop(resolved_candidates.index(folder_resolved))
            candidates.insert(0, folder_path)

        if candidates:
            return candidates[0], candidates

        if folder_path.exists() and not folder_path.is_dir():
            logger.error(f"Files folder '{folder_path}' is not a directory. Skipping...")
            return None, []

        if not folder_path.exists():
            logger.error(f"Files folder '{folder_path}' does not exist. Skipping...")
            return None, []

        if folder_path.exists() and folder_path.is_dir():
            return folder_path, []

        return folder_path, []

    def _create_or_identify_vector_store(self, folder_path: Path) -> str | None:
        """Create vector store and rename folder, or extract existing VS ID from path."""
        vs_id_match = re.search(r"(.+)_(vs_[a-zA-Z0-9]{15,})$", str(folder_path))

        if vs_id_match:
            if not folder_path.exists():
                logger.error(
                    f"Agent {self.agent.name}: Expected vector store folder '{folder_path}' but it does not exist."
                )
                return None

            if not folder_path.is_dir():
                logger.error(f"Files folder '{folder_path}' is not a directory. Skipping...")
                return None

            self.agent.files_folder_path = folder_path.resolve()
            return vs_id_match.group(2)

        logger.info(
            f"Agent {self.agent.name}: files_folder '{folder_path}' does not specify a Vector Store ID. "
            "Creating a new Vector Store."
        )
        created_vs = self.agent.client_sync.vector_stores.create(name=folder_path.name)
        new_folder_path = folder_path.parent / f"{folder_path.name}_{created_vs.id}"

        try:
            if folder_path.exists() and folder_path.name != new_folder_path.name:
                folder_path.rename(new_folder_path)
                logger.info(f"Agent {self.agent.name}: Renamed folder to {new_folder_path}")
            elif not folder_path.exists():
                new_folder_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"Agent {self.agent.name}: Created files folder {new_folder_path}")

            self.agent.files_folder_path = new_folder_path.resolve()
            return created_vs.id
        except Exception as e:
            logger.error(f"Agent {self.agent.name}: Error renaming/creating files_folder to {new_folder_path}: {e}")
            return None

    def _find_new_files_to_process(self, original_folder_path: Path) -> list[Path]:
        """Find new files in the original directory that aren't in the VS folder yet."""
        if not original_folder_path.exists():
            return []

        processed_files = set()
        for vs_file in self.agent.files_folder_path.iterdir():
            if vs_file.is_file() and "_file-" in vs_file.name:
                original_name = vs_file.name.split("_file-")[0] + vs_file.suffix
                processed_files.add(original_name)

        new_files = []
        for original_file in original_folder_path.iterdir():
            if original_file.is_file() and original_file.name not in processed_files:
                if self._should_skip_file(original_file.name):
                    logger.debug(f"Skipping file '{original_file.name}'")
                    continue
                logger.info(f"Agent {self.agent.name}: Found new file to process: {original_file.name}")
                new_files.append(original_file)

        return new_files

    def _upload_file_by_type(self, file_path: Path, include_in_vs: bool = True) -> str | None:
        """Upload file; return file_id for code interpreter types, else None."""
        ext = file_path.suffix.lower()

        if ext in CODE_INTERPRETER_FILE_EXTENSIONS + IMAGE_FILE_EXTENSIONS:
            return self.upload_file(str(file_path), include_in_vector_store=False)
        elif ext in FILE_SEARCH_FILE_EXTENSIONS:
            self.upload_file(str(file_path))
            return None
        else:
            raise AgentsException(f"Unsupported file extension: {ext} for file {file_path}")
