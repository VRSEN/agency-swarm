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
        existing_data_str = json.dumps(existing_data)
        if len(existing_data_str) > 2000:
            existing_data_str = existing_data_str[: 2000]
        return {"file_path": file_path, "file_content": existing_data_str}
        