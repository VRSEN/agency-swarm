from agency_swarm.tools import BaseTool
import json
import os
from pydantic import Field

class ReadJsonFile(BaseTool):
    """Read a JSON File"""
    file_name: str = Field(
        ..., description="需要读取的json文件名称"
    )

    def run(self):
        current_dir = os.path.join("agents", "files")
        file_path = os.path.join(current_dir, self.file_name)
        print(file_path)
        try:
            with open(file_path, 'r') as f:
                existing_data = json.load(f)
        except:
            existing_data = []
        return existing_data
        