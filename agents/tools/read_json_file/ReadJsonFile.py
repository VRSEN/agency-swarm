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
        agents_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        file_path = os.path.join(agents_dir, "files", self.file_name)
        print(file_path)
        if self.file_name.find('api_results') != -1:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except:
                print("context file is empty or read wrong")
                existing_data = []
        else:
            try:
                with open(file_path, 'r') as f:
                    existing_data = json.load(f)
            except:
                print("context file is empty or read wrong")
                existing_data = []
        existing_data_str = json.dumps(existing_data)
        if len(existing_data_str) > 20000:
            existing_data_str = existing_data_str[: 20000]
        return {"file_path": file_path, "file_content": existing_data_str}
        