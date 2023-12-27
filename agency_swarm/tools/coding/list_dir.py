from pydantic import Field

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
        import os

        tree = []
        def list_directory_tree(path, indent=''):
            """Recursively list the contents of a directory in a tree-like format."""
            if not os.path.isdir(path):
                raise ValueError(f"The path {path} is not a valid directory")

            items = os.listdir(path)
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

