from agency_swarm.tools import BaseTool
import json
import os
from pydantic import Field

class ReadContexts(BaseTool):
    """Read Files"""
    files_path_name: str = Field(
        ..., description="需要读取的contexts路径名"
    )

    def run(self):
        current_dir = os.path.join("agents", "files")
        files_path = os.path.join(current_dir, self.files_path_name)
        print(files_path)
        result = {}
        for filename in os.listdir(files_path):
            if filename.endswith(".json"):
                file_path = os.path.join(files_path, filename)
                try:
                    with open(file_path, 'r') as f:
                        existing_data = json.load(f)
                except:
                    existing_data = []
                result[filename] = existing_data
        return result
