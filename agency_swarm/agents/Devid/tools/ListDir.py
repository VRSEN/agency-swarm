from pydantic import Field, field_validator

from agency_swarm import BaseTool
import os


class ListDir(BaseTool):
    """
    This tool returns the tree structure of the directory.
    """
    dir_path: str = Field(
        ..., description="Path of the directory to read.",
        examples=["./", "./test", "../../"]
    )

    def run(self):
        tree = []

        def list_directory_tree(path, indent=''):
            """Recursively list the contents of a directory in a tree-like format."""
            if not os.path.isdir(path):
                raise ValueError(f"The path {path} is not a valid directory")

            items = os.listdir(path)
            # exclude common hidden files and directories
            exclude = ['.git', '.idea', '__pycache__', 'node_modules', '.venv', '.gitignore', '.gitkeep',
                       '.DS_Store', '.vscode', '.next', 'dist', 'build', 'out', 'venv', 'env', 'logs', 'data']

            items = [item for item in items if item not in exclude]

            for i, item in enumerate(items):
                item_path = os.path.join(path, item)
                if i < len(items) - 1:
                    tree.append(indent + '├── ' + item)
                    if os.path.isdir(item_path):
                        list_directory_tree(item_path, indent + '│   ')
                else:
                    tree.append(indent + '└── ' + item)
                    if os.path.isdir(item_path):
                        list_directory_tree(item_path, indent + '    ')

        list_directory_tree(self.dir_path)

        return "\n".join(tree)

    @field_validator("dir_path", mode='after')
    @classmethod
    def validate_dir_path(cls, v):
        if "file-" in v:
            raise ValueError("You tried to access an openai file with a local directory reader tool. "
                             "Please use the `myfiles_browser` tool to access openai directories instead.")

        if not os.path.isdir(v):
            if "/mnt/data" in v:
                raise ValueError("You tried to access an openai file directory with a local directory reader tool. "
                                 "Please use the `myfiles_browser` tool to access openai files instead. "
                                 "You can work in your local directory by using the `FileReader` tool.")

            raise ValueError(f"The path {v} is not a valid directory")
        return v
