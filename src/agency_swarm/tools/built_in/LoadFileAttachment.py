from pathlib import Path

from pydantic import Field

from agency_swarm.tools.base_tool import BaseTool
from agency_swarm.tools.utils import tool_output_file_from_path, tool_output_image_from_path


class LoadFileAttachment(BaseTool):  # type: ignore[misc]
    """
    Loads a file attachment and returns it in the appropriate format for the agent to view.
    Supports images (jpg, png, gif, etc.) and PDF files.

    Accepts both absolute paths and paths relative to the current working directory.
    """

    path: Path = Field(
        ..., description="Path to the file to load. Can be absolute or relative to the current working directory."
    )

    def _is_image_file(self, file_path: Path) -> bool:
        """
        Check if file is an image based on its extension.
        """
        image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".svg"}
        return file_path.suffix.lower() in image_extensions

    async def run(self):
        """
        Analyzes the file and returns it in the appropriate format.
        If the file doesn't exist, provides a list of available files in the directory.
        """
        # Resolve path relative to CWD if it's relative
        resolved_path = self.path if self.path.is_absolute() else Path.cwd() / self.path

        # Step 1: Check if file exists
        if not resolved_path.exists():
            # Get the directory to search in
            directory = resolved_path.parent if resolved_path.parent.exists() else Path.cwd()

            # List all files in the directory
            if directory.exists():
                files = [f.name for f in directory.iterdir() if f.is_file()]
                if files:
                    files_list = "\n".join(f"- {f}" for f in sorted(files))
                    return f"File not found: {resolved_path}\n\nAvailable files in {directory}:\n{files_list}"
                else:
                    return f"File not found: {resolved_path}\n\nThe directory {directory} is empty."
            else:
                return f"File not found: {resolved_path}\n\nThe directory {directory} does not exist."

        # Step 2: Check if the file is an image
        is_image = self._is_image_file(resolved_path)

        # Step 3: Return appropriate output type
        if is_image:
            return tool_output_image_from_path(resolved_path, detail="auto")
        else:
            return tool_output_file_from_path(resolved_path)
