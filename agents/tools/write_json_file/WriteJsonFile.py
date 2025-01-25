from agency_swarm.tools import BaseTool
import json
import os
from pydantic import Field

class WriteJsonFile(BaseTool):
    """Write a JSON File"""
    file_name: str = Field(
        ..., description="需要写入的json文件名称"
    )
    message: str = Field(
        ..., description="需要在该json文件中写入的内容"
    )

    def run(self):
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        file_path = os.path.join(agents_dir, "files", self.file_name)
        try:
            with open(file_path, 'r') as f:
                existing_data = json.load(f)
        except:
            existing_data = []
        
        new_data = json.loads(self.message)
        if isinstance(existing_data, list):
            existing_data.append(new_data)
        elif isinstance(existing_data, dict):
            existing_data.update(new_data)
        else:
            raise ValueError("JSON 文件中的数据必须是列表或字典")

        with open(file_path, 'w') as f:
            json.dump(existing_data, f, indent=4)