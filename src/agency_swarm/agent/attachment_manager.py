import logging
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agents import CodeInterpreterTool, TResponseInputItem
from agents.exceptions import AgentsException
from agents.items import ItemHelpers

if TYPE_CHECKING:
    from agency_swarm import Agent

from .file_manager import CODE_INTERPRETER_FILE_EXTENSIONS, FILE_SEARCH_FILE_EXTENSIONS, IMAGE_FILE_EXTENSIONS

logger = logging.getLogger(__name__)


class AttachmentManager:
    """Manages temporary file attachments for agent requests."""

    def __init__(self, agent: "Agent"):
        self.agent = agent

        if not agent.file_manager:
            raise AgentsException(
                f"Cannot use AttachmentManager for agent {agent.name} without file manager. "
                "Please initialize the agent with a valid 'files_folder'."
            )

        # Temp variables used to hold attachment data to be used in cleanup
        self._temp_code_interpreter_file_ids: list[str] = []

    def init_attachments_vs(self, vs_name: str = "attachments_vs"):
        """
        Create or retrieve a temporary vector store for attachments.

        Args:
            vs_name: Name for the temporary vector store

        Returns:
            str: Vector store ID
        """
        logger.info(f"Attachments vector store for agent {self.agent.name}: {vs_name}")
        existing_vs = self.agent.client_sync.vector_stores.list()
        existing_vs_names = [vs.name for vs in existing_vs.data]
        if vs_name in existing_vs_names:
            return existing_vs.data[existing_vs_names.index(vs_name)].id
        else:
            created_vs = self.agent.client_sync.vector_stores.create(name=vs_name)
            return created_vs.id

    async def sort_file_attachments(self, file_ids: list[str]) -> list[dict]:
        """
        Sort file attachments by type and prepare them for processing.

        Args:
            file_ids: List of OpenAI file IDs

        Returns:
            list: Content items for PDF files that can be directly attached to messages
        """
        pdf_file_ids = []
        code_interpreter_ids = []
        image_file_ids = []

        for file_id in file_ids:
            filename = self._get_filename_by_id(file_id)
            extension = Path(filename).suffix.lower()
            # Use code interpreter for all file types except .go, pdf, and images
            code_interpreter_extensions = [
                ext
                for ext in CODE_INTERPRETER_FILE_EXTENSIONS + FILE_SEARCH_FILE_EXTENSIONS
                if ext not in [".go", ".pdf"]
            ]
            if extension in code_interpreter_extensions:
                code_interpreter_ids.append(file_id)
            elif extension == ".pdf":
                pdf_file_ids.append(file_id)
            elif extension in IMAGE_FILE_EXTENSIONS:
                image_file_ids.append(file_id)
            else:
                raise AgentsException(f"Unsupported file extension: {extension} for file {filename}")

        # Add PDF file and images to content (they can be directly attached to messages)
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

        for file_id in image_file_ids:
            if isinstance(file_id, str) and file_id.startswith("file-"):
                logger.debug(f"Adding image file content item for file_id: {file_id}")
                file_content_item = {
                    "type": "input_image",
                    "file_id": file_id,
                }
                content_list.append(file_content_item)
                logger.debug(f"Added file content item for file_id: {file_id}")
            else:
                logger.warning(f"Invalid file_id format: {file_id} for agent {self.agent.name}")

        # Add temporary tools for other file types
        if code_interpreter_ids:
            logger.info(f"Adding file ids: {code_interpreter_ids} for {self.agent.name}'s code interpreter")
            self.agent.file_manager.add_code_interpreter_tool(code_interpreter_ids)  # type: ignore[union-attr]
            self._temp_code_interpreter_file_ids = code_interpreter_ids

        return content_list

    def attachments_cleanup(self):
        """
        Clean up temporary attachments and reset agent to initial state.
        """
        if self._temp_code_interpreter_file_ids:
            # Remove temporary files from CodeInterpreterTool
            for tool in self.agent.tools:
                if isinstance(tool, CodeInterpreterTool):
                    code_interpreter_container = tool.tool_config.get("container", {})
                    if isinstance(code_interpreter_container, str):
                        logger.warning(f"Agent {self.agent.name}: Cannot modify container directly for file removal")
                        break
                    file_ids_list = code_interpreter_container.get("file_ids", [])
                    for file_id in self._temp_code_interpreter_file_ids:
                        if file_id in file_ids_list:
                            file_ids_list.remove(file_id)
                            if len(file_ids_list) == 0:
                                self.agent.tools.remove(tool)
                                logger.debug(f"Removed temp CodeInterpreterTool from {self.agent.name}")
                            else:
                                logger.debug(f"Removed attachment file {file_id} from CodeInterpreterTool")
                    code_interpreter_container["file_ids"] = file_ids_list
                    tool.tool_config["container"] = code_interpreter_container

        # Reset temp variables
        self._temp_code_interpreter_file_ids = []

    def _get_filename_by_id(self, file_id: str) -> str:
        """Get the filename of a file by its ID"""
        file_data = self.agent.client_sync.files.retrieve(file_id)
        return file_data.filename

    async def prepare_and_attach_files(
        self,
        processed_current_message_items: list[TResponseInputItem],
        file_ids: list[str] | None,
        message_files: list[str] | None,
        kwargs: dict[str, Any],
    ) -> None:
        """Handle file attachments for messages."""
        files_to_attach = file_ids or message_files or kwargs.get("file_ids") or kwargs.get("message_files")
        if files_to_attach and isinstance(files_to_attach, list):
            # Warn about deprecated message_files usage
            if message_files or kwargs.get("message_files"):
                warnings.warn(
                    "'message_files' parameter is deprecated. Use 'file_ids' instead.",
                    DeprecationWarning,
                    stacklevel=3,
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

                    file_content_items = await self.sort_file_attachments(files_to_attach)
                    content_list.extend(file_content_items)

                    # Update the message content
                    if content_list != []:
                        last_message["content"] = content_list  # type: ignore[typeddict-unknown-key, arg-type]
                else:
                    logger.warning(
                        f"Cannot attach files: Last message is not a user message for agent {self.agent.name}"
                    )
            else:
                logger.warning(f"Cannot attach files: No messages to attach to for agent {self.agent.name}")

    async def process_message_and_files(
        self,
        message: str | list[TResponseInputItem],
        file_ids: list[str] | None,
        message_files: list[str] | None,
        kwargs: dict[str, Any],
        method_name: str = "execution",
    ) -> list[TResponseInputItem]:
        """Process message and handle file attachments. Returns processed_items."""
        # Process current message items
        try:
            processed_current_message_items = ItemHelpers.input_to_new_input_list(message)
        except Exception as e:
            logger.error(f"Error processing current input message for {method_name}: {e}", exc_info=True)
            raise AgentsException(f"Failed to process input message for agent {self.agent.name}") from e

        # Handle file attachments
        await self.prepare_and_attach_files(processed_current_message_items, file_ids, message_files, kwargs)

        return processed_current_message_items
